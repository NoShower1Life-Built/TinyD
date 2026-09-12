from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4


class SchedulableEvent(Protocol):
    event_id: str
    tenant_id: str
    aggregate_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class WorkItem:
    work_id: UUID
    tenant_id: str
    aggregate_id: str
    run_id: str
    event_id: str
    status: str
    attempt_count: int
    available_at: datetime
    lease_owner: str | None
    lease_token: UUID | None
    lease_expires_at: datetime | None
    last_error: str | None
    created_at: datetime
    completed_at: datetime | None


class DurableScheduler:
    """PostgreSQL-backed durable work-item scheduler.

    Scheduling state is coordination state. The event ledger remains the
    authoritative event history. Work items are created only for events that
    already exist in that ledger.

    ``complete`` and ``fail`` retain a temporary owner-only compatibility path
    for the existing Worker. The hardened Worker must pass the lease token;
    the compatibility path is not considered fencing-complete.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def submit(self, event: SchedulableEvent, *, available_at: datetime | None = None) -> WorkItem:
        _validate_event_identity(event)
        when = _utc(available_at or datetime.now(timezone.utc))
        created_at = datetime.now(timezone.utc)
        work_id = uuid4()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_id, tenant_id, aggregate_id, run_id
                FROM tinyd_events
                WHERE event_id = %s
                """,
                (event.event_id,),
            )
            ledger_event = cursor.fetchone()
            if ledger_event is None:
                self._connection.rollback()
                raise ValueError("event must be durably persisted before scheduling")
            if tuple(ledger_event) != (
                event.event_id, event.tenant_id, event.aggregate_id, event.run_id
            ):
                self._connection.rollback()
                raise ValueError("event identity does not match authoritative ledger")

            cursor.execute(
                """
                INSERT INTO tinyd_work_items (
                    work_id, tenant_id, aggregate_id, run_id, event_id,
                    status, attempt_count, available_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, 'PENDING', 0, %s, %s)
                ON CONFLICT (tenant_id, event_id) DO NOTHING
                RETURNING work_id, tenant_id, aggregate_id, run_id, event_id,
                          status, attempt_count, available_at, lease_owner,
                          lease_token, lease_expires_at, last_error, created_at, completed_at
                """,
                (
                    str(work_id), event.tenant_id, event.aggregate_id, event.run_id,
                    event.event_id, when, created_at,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    SELECT work_id, tenant_id, aggregate_id, run_id, event_id,
                           status, attempt_count, available_at, lease_owner,
                           lease_token, lease_expires_at, last_error, created_at, completed_at
                    FROM tinyd_work_items
                    WHERE tenant_id = %s AND event_id = %s
                    """,
                    (event.tenant_id, event.event_id),
                )
                row = cursor.fetchone()
                if row is None:
                    self._connection.rollback()
                    raise RuntimeError("durable work item disappeared after idempotent submit")
            self._connection.commit()
        return _row_to_work_item(row)

    def claim(self, worker_id: str, *, lease_duration: timedelta) -> WorkItem | None:
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        now = datetime.now(timezone.utc)
        expires = now + lease_duration
        lease_token = uuid4()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT work_id, tenant_id, aggregate_id, run_id, event_id,
                       status, attempt_count, available_at, lease_owner,
                       lease_token, lease_expires_at, last_error, created_at, completed_at
                FROM tinyd_work_items
                WHERE (
                    status = 'PENDING' AND available_at <= %s
                ) OR (
                    status = 'LEASED' AND lease_expires_at <= %s
                )
                ORDER BY available_at ASC, work_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (now, now),
            )
            row = cursor.fetchone()
            if row is None:
                self._connection.commit()
                return None
            work_id = row[0]
            cursor.execute(
                """
                UPDATE tinyd_work_items
                SET status = 'LEASED',
                    lease_owner = %s,
                    lease_token = %s,
                    lease_expires_at = %s,
                    attempt_count = attempt_count + 1
                WHERE work_id = %s
                RETURNING work_id, tenant_id, aggregate_id, run_id, event_id,
                          status, attempt_count, available_at, lease_owner,
                          lease_token, lease_expires_at, last_error, created_at, completed_at
                """,
                (worker_id, str(lease_token), expires, work_id),
            )
            claimed = cursor.fetchone()
            if claimed is None:
                self._connection.rollback()
                raise RuntimeError("claimed work item disappeared during lease update")
            self._connection.commit()
        return _row_to_work_item(claimed)

    def renew(self, work_id: UUID, worker_id: str, lease_token: UUID, *, lease_duration: timedelta) -> bool:
        _validate_lease_arguments(worker_id, lease_token, lease_duration)
        now = datetime.now(timezone.utc)
        expires = now + lease_duration
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tinyd_work_items
                SET lease_expires_at = %s
                WHERE work_id = %s
                  AND status = 'LEASED'
                  AND lease_owner = %s
                  AND lease_token = %s
                  AND lease_expires_at > %s
                """,
                (expires, str(work_id), worker_id, str(lease_token), now),
            )
            updated = cursor.rowcount
            self._connection.commit()
        return updated == 1

    def complete(self, work_id: UUID, worker_id: str, lease_token: UUID | None = None) -> bool:
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        with self._connection.cursor() as cursor:
            if lease_token is None:
                cursor.execute(
                    """
                    UPDATE tinyd_work_items
                    SET status = 'COMPLETED', completed_at = %s,
                        lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, last_error = NULL
                    WHERE work_id = %s AND status = 'LEASED'
                      AND lease_owner = %s AND lease_expires_at > %s
                    """,
                    (datetime.now(timezone.utc), str(work_id), worker_id, datetime.now(timezone.utc)),
                )
            else:
                if not isinstance(lease_token, UUID):
                    raise ValueError("lease_token must be a UUID")
                cursor.execute(
                    """
                    UPDATE tinyd_work_items
                    SET status = 'COMPLETED', completed_at = %s,
                        lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, last_error = NULL
                    WHERE work_id = %s AND status = 'LEASED'
                      AND lease_owner = %s AND lease_token = %s
                    """,
                    (datetime.now(timezone.utc), str(work_id), worker_id, str(lease_token)),
                )
            updated = cursor.rowcount
            self._connection.commit()
        return updated == 1

    def fail(
        self,
        work_id: UUID,
        worker_id: str,
        lease_token_or_error: UUID | str,
        error: str | None = None,
        *,
        retry_at: datetime | None,
        max_attempts: int,
    ) -> bool:
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if isinstance(lease_token_or_error, UUID):
            lease_token = lease_token_or_error
            failure = error
        else:
            lease_token = None
            failure = lease_token_or_error
        if not failure:
            raise ValueError("error must not be empty")
        when = _utc(retry_at) if retry_at is not None else None
        with self._connection.cursor() as cursor:
            if lease_token is None:
                cursor.execute(
                    """
                    UPDATE tinyd_work_items
                    SET status = CASE WHEN attempt_count >= %s THEN 'FAILED' ELSE 'PENDING' END,
                        available_at = CASE WHEN attempt_count >= %s THEN available_at ELSE COALESCE(%s, available_at) END,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                        last_error = %s
                    WHERE work_id = %s AND status = 'LEASED'
                      AND lease_owner = %s AND lease_expires_at > %s
                    """,
                    (max_attempts, max_attempts, when, failure, str(work_id), worker_id, datetime.now(timezone.utc)),
                )
            else:
                if not isinstance(lease_token, UUID):
                    raise ValueError("lease_token must be a UUID")
                cursor.execute(
                    """
                    UPDATE tinyd_work_items
                    SET status = CASE WHEN attempt_count >= %s THEN 'FAILED' ELSE 'PENDING' END,
                        available_at = CASE WHEN attempt_count >= %s THEN available_at ELSE COALESCE(%s, available_at) END,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                        last_error = %s
                    WHERE work_id = %s AND status = 'LEASED'
                      AND lease_owner = %s AND lease_token = %s
                    """,
                    (max_attempts, max_attempts, when, failure, str(work_id), worker_id, str(lease_token)),
                )
            updated = cursor.rowcount
            self._connection.commit()
        return updated == 1

    def reclaim_expired(self, *, limit: int = 100) -> int:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                WITH expired AS (
                    SELECT work_id FROM tinyd_work_items
                    WHERE status = 'LEASED' AND lease_expires_at <= %s
                    ORDER BY lease_expires_at ASC, work_id ASC
                    FOR UPDATE SKIP LOCKED LIMIT %s
                )
                UPDATE tinyd_work_items AS w
                SET status = 'PENDING', lease_owner = NULL,
                    lease_token = NULL, lease_expires_at = NULL
                FROM expired WHERE w.work_id = expired.work_id
                """,
                (datetime.now(timezone.utc), limit),
            )
            count = cursor.rowcount
            self._connection.commit()
        return count


def _validate_event_identity(event: SchedulableEvent) -> None:
    for name in ("event_id", "tenant_id", "aggregate_id", "run_id"):
        if not isinstance(getattr(event, name, None), str) or not getattr(event, name):
            raise ValueError(f"event.{name} must be a non-empty string")


def _validate_lease_arguments(worker_id: str, lease_token: UUID, lease_duration: timedelta) -> None:
    if not worker_id:
        raise ValueError("worker_id must not be empty")
    if not isinstance(lease_token, UUID):
        raise ValueError("lease_token must be a UUID")
    if lease_duration <= timedelta(0):
        raise ValueError("lease_duration must be positive")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _row_to_work_item(row: tuple[Any, ...]) -> WorkItem:
    if len(row) != 14:
        raise ValueError("invalid tinyd_work_items row")
    return WorkItem(
        work_id=UUID(str(row[0])), tenant_id=row[1], aggregate_id=row[2], run_id=row[3], event_id=row[4],
        status=row[5], attempt_count=int(row[6]), available_at=_utc(row[7]), lease_owner=row[8],
        lease_token=UUID(str(row[9])) if row[9] is not None else None,
        lease_expires_at=_utc(row[10]) if row[10] is not None else None,
        last_error=row[11], created_at=_utc(row[12]),
        completed_at=_utc(row[13]) if row[13] is not None else None,
    )
