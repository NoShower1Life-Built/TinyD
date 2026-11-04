from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from typing import Any
from uuid import UUID, uuid5

import psycopg
from psycopg.rows import dict_row

from packages.contracts.src.envelope import EventEnvelope, EventIntegrity
from packages.runtime.src.journal import PostgresEventJournal


class WorkerError(RuntimeError):
    """Base error for durable worker failures."""


class LeaseLost(WorkerError):
    """The worker no longer owns the current lease generation."""


class NoHandlerRegistered(WorkerError):
    """A persisted task requests an operation with no registered implementation."""


class DurableWorker:
    """PostgreSQL-leased worker with fenced claims and atomic terminal commits.

    Task execution is at-least-once across lease expiry. A worker may commit only
    while its monotonically increasing lease generation remains current. Terminal
    task state and its authoritative journal event share one PostgreSQL transaction.
    """

    def __init__(self, dsn: str, worker_id: str | None = None, lease_seconds: int = 60) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        if lease_seconds < 5:
            raise ValueError("lease_seconds must be >= 5")
        self.dsn = dsn
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.lease_seconds = lease_seconds
        self.journal = PostgresEventJournal(dsn)
        self.initialize()

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tinyd_worker_tasks (
                    event_id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    run_id UUID NOT NULL,
                    payload JSONB NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','failed')),
                    worker_id TEXT,
                    lease_until TIMESTAMPTZ,
                    lease_generation BIGINT NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    result JSONB,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (tenant_id, run_id)
                )
                """
            )
            # Upgrade installations created before lease fencing was introduced.
            conn.execute(
                "ALTER TABLE tinyd_worker_tasks ADD COLUMN IF NOT EXISTS "
                "lease_generation BIGINT NOT NULL DEFAULT 0"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS tinyd_worker_tasks_claim_idx "
                "ON tinyd_worker_tasks (status, lease_until, created_at)"
            )

    def _materialize_pending(self, conn) -> None:
        # The journal is authoritative; this is repeatable and safe across workers.
        conn.execute(
            """
            INSERT INTO tinyd_worker_tasks
                (event_id, tenant_id, run_id, payload, status)
            SELECT event_id, tenant_id, run_id, event->'payload', 'pending'
            FROM tinyd_event_journal
            WHERE event_type = 'run.requested' AND run_id IS NOT NULL
            ON CONFLICT (event_id) DO NOTHING
            """
        )

    def _reconcile_terminal_outcomes(self, conn) -> None:
        """Repair terminal task rows left without journal evidence by older workers."""
        rows = conn.execute(
            """
            SELECT task.event_id, task.tenant_id, task.run_id, task.attempts,
                   task.lease_generation, task.result, task.error, task.status
            FROM tinyd_worker_tasks AS task
            WHERE task.status IN ('succeeded', 'failed')
              AND NOT EXISTS (
                  SELECT 1
                  FROM tinyd_event_journal AS event
                  WHERE event.tenant_id = task.tenant_id
                    AND event.aggregate_type = 'run'
                    AND event.aggregate_id = task.run_id
                    AND event.event_type IN ('run.succeeded', 'run.failed')
              )
            ORDER BY task.updated_at, task.event_id
            FOR UPDATE OF task SKIP LOCKED
            """
        ).fetchall()
        for row in rows:
            task = dict(row)
            if task["status"] == "succeeded":
                payload = {
                    **(task["result"] or {}),
                    "lease_generation": task["lease_generation"],
                    "recovered": True,
                }
                self._append_transition(conn, task, "run.succeeded", payload)
            else:
                payload = {
                    "error": task["error"] or "terminal failure recovered without journal evidence",
                    "attempt": task["attempts"],
                    "lease_generation": task["lease_generation"],
                    "recovered": True,
                }
                self._append_transition(conn, task, "run.failed", payload)

    def claim_next(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.transaction():
                self._materialize_pending(conn)
                self._reconcile_terminal_outcomes(conn)
                row = conn.execute(
                    """
                    WITH candidate AS (
                        SELECT event_id
                        FROM tinyd_worker_tasks
                        WHERE status = 'pending'
                           OR (status = 'running' AND lease_until <= NOW())
                        ORDER BY created_at, event_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE tinyd_worker_tasks AS task
                    SET status = 'running',
                        worker_id = %s,
                        lease_until = NOW() + (%s * INTERVAL '1 second'),
                        lease_generation = task.lease_generation + 1,
                        attempts = task.attempts + 1,
                        updated_at = NOW(),
                        error = NULL
                    FROM candidate
                    WHERE task.event_id = candidate.event_id
                    RETURNING task.event_id, task.tenant_id, task.run_id, task.payload,
                              task.attempts, task.lease_until, task.lease_generation
                    """,
                    (self.worker_id, self.lease_seconds),
                ).fetchone()
                return dict(row) if row else None

    @staticmethod
    def _execute_payload(payload: dict[str, Any]) -> dict[str, Any]:
        operation = payload.get("operation")
        if operation == "canonicalize_json":
            value = payload.get("value")
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            return {"operation": operation, "canonical_json": canonical}
        if operation == "sha256":
            value = payload.get("value")
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            return {"operation": operation, "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}
        raise NoHandlerRegistered(f"no worker handler registered for operation: {operation!r}")

    def _assert_current_lease(self, conn, task: dict[str, Any]) -> None:
        row = conn.execute(
            """
            SELECT 1 FROM tinyd_worker_tasks
            WHERE event_id=%s AND status='running' AND worker_id=%s
              AND lease_generation=%s AND lease_until > NOW()
            FOR UPDATE
            """,
            (task["event_id"], self.worker_id, task["lease_generation"]),
        ).fetchone()
        if row is None:
            raise LeaseLost("worker lease was lost or superseded")

    def _append_transition(
        self,
        conn,
        task: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
    ) -> EventEnvelope:
        history = self.journal.history(task["tenant_id"], "run", task["run_id"], conn=conn)
        if not history:
            raise WorkerError("claimed task has no authoritative run.requested event")
        last = history[-1]
        event_attempt = task["attempts"] if event_type in {"run.started", "run.failed"} else 1
        event_id = uuid5(
            task["tenant_id"],
            f"tinyd:worker:{task['event_id']}:{event_type}:attempt:{event_attempt}:v1",
        )
        transition = EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            event_version=1,
            tenant_id=task["tenant_id"],
            agent_id=last.agent_id,
            run_id=task["run_id"],
            task_id=task["run_id"],
            correlation_id=last.correlation_id,
            causation_id=last.event_id,
            aggregate_type="run",
            aggregate_id=task["run_id"],
            sequence=last.sequence + 1,
            producer=f"tinyd-worker:{self.worker_id}",
            payload=payload,
            integrity=EventIntegrity(previous_digest=last.integrity.digest, digest="pending"),
        )
        transition = transition.model_copy(update={
            "integrity": EventIntegrity(
                previous_digest=last.integrity.digest,
                digest=self.journal.calculate_digest(transition, last.integrity.digest),
            )
        })
        return self.journal.append(transition, conn=conn)

    def _append_started(self, task: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.transaction():
                self._assert_current_lease(conn, task)
                self._append_transition(
                    conn, task, "run.started",
                    {"worker_id": self.worker_id, "attempt": task["attempts"],
                     "lease_generation": task["lease_generation"]},
                )

    def _commit_success(self, task: dict[str, Any], result: dict[str, Any]) -> None:
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        with self._connect() as conn:
            with conn.transaction():
                self._assert_current_lease(conn, task)
                updated = conn.execute(
                    """
                    UPDATE tinyd_worker_tasks
                    SET status='succeeded', result=%s::jsonb, lease_until=NULL,
                        worker_id=NULL, updated_at=NOW()
                    WHERE event_id=%s AND status='running' AND worker_id=%s
                      AND lease_generation=%s
                    RETURNING event_id
                    """,
                    (encoded, task["event_id"], self.worker_id, task["lease_generation"]),
                ).fetchone()
                if updated is None:
                    raise LeaseLost("worker lease was lost before success could be committed")
                self._append_transition(conn, task, "run.succeeded", {**result, "lease_generation": task["lease_generation"]})

    def _commit_failure(self, task: dict[str, Any], message: str) -> None:
        with self._connect() as conn:
            with conn.transaction():
                self._assert_current_lease(conn, task)
                updated = conn.execute(
                    """
                    UPDATE tinyd_worker_tasks
                    SET status='failed', error=%s, lease_until=NULL,
                        worker_id=NULL, updated_at=NOW()
                    WHERE event_id=%s AND status='running' AND worker_id=%s
                      AND lease_generation=%s
                    RETURNING event_id
                    """,
                    (message, task["event_id"], self.worker_id, task["lease_generation"]),
                ).fetchone()
                if updated is None:
                    raise LeaseLost("worker lease was lost before failure could be committed")
                self._append_transition(
                    conn, task, "run.failed",
                    {"error": message, "attempt": task["attempts"],
                     "lease_generation": task["lease_generation"]},
                )

    def run_once(self) -> dict[str, Any] | None:
        task = self.claim_next()
        if task is None:
            return None
        self._append_started(task)
        try:
            result = self._execute_payload(task["payload"] or {})
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"[:2000]
            self._commit_failure(task, message)
            return {"event_id": str(task["event_id"]), "status": "failed", "error": message}
        self._commit_success(task, result)
        return {"event_id": str(task["event_id"]), "status": "succeeded", "result": result}

    def run_forever(self, poll_seconds: float = 0.5) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        while True:
            result = self.run_once()
            if result is None:
                time.sleep(poll_seconds)


def main() -> None:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    DurableWorker(dsn, worker_id=os.getenv("TINYD_WORKER_ID") or None).run_forever()


if __name__ == "__main__":
    main()
