from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .types import ExecutionRecord, ExecutionState


class ExecutionLedger:
    """Durable SQLite execution store with task/source/execution uniqueness and leases."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS executions (execution_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, source_revision TEXT NOT NULL, state TEXT NOT NULL, started_at TEXT, finished_at TEXT, exit_code INTEGER, output TEXT, error TEXT, metadata TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_executions_task ON executions(task_id, source_revision)")
            db.execute("CREATE TABLE IF NOT EXISTS execution_leases (execution_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, source_revision TEXT NOT NULL, owner TEXT NOT NULL, acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_execution_leases_expiry ON execution_leases(expires_at)")
            db.commit()

    def put(self, record: ExecutionRecord) -> ExecutionRecord:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)", (record.execution_id, record.task_id, record.source_revision, record.state.value, record.started_at, record.finished_at, record.exit_code, record.output, record.error, json.dumps(record.metadata or {}, sort_keys=True)))
            db.commit()
        return record

    def get(self, execution_id: str) -> ExecutionRecord | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT * FROM executions WHERE execution_id=?", (execution_id,)).fetchone()
        if row is None: return None
        return ExecutionRecord(row[0], row[1], row[2], ExecutionState(row[3]), row[4], row[5], row[6], row[7], row[8], json.loads(row[9]))

    def for_task(self, task_id: str, source_revision: str | None = None) -> list[ExecutionRecord]:
        query = "SELECT * FROM executions WHERE task_id=?"; args: list[str] = [task_id]
        if source_revision is not None: query += " AND source_revision=?"; args.append(source_revision)
        query += " ORDER BY started_at, execution_id"
        with sqlite3.connect(self.path) as db: rows = db.execute(query, args).fetchall()
        return [ExecutionRecord(r[0],r[1],r[2],ExecutionState(r[3]),r[4],r[5],r[6],r[7],r[8],json.loads(r[9])) for r in rows]

    def all(self) -> Iterable[ExecutionRecord]:
        with sqlite3.connect(self.path) as db: rows = db.execute("SELECT * FROM executions ORDER BY started_at, execution_id").fetchall()
        return [ExecutionRecord(r[0],r[1],r[2],ExecutionState(r[3]),r[4],r[5],r[6],r[7],r[8],json.loads(r[9])) for r in rows]

    def acquire_lease(self, execution_id: str, task_id: str, source_revision: str, owner: str, lease_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=lease_seconds)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner, expires_at FROM execution_leases WHERE execution_id=?", (execution_id,)).fetchone()
            if row is not None and row[0] != owner and datetime.fromisoformat(row[1]) > now:
                db.rollback()
                return False
            db.execute("INSERT OR REPLACE INTO execution_leases VALUES (?,?,?,?,?,?)", (execution_id, task_id, source_revision, owner, now.isoformat(), expires.isoformat()))
            db.commit()
        return True

    def release_lease(self, execution_id: str, owner: str) -> bool:
        with sqlite3.connect(self.path) as db:
            changed = db.execute("DELETE FROM execution_leases WHERE execution_id=? AND owner=?", (execution_id, owner)).rowcount
            db.commit()
        return changed == 1

    def recover_expired(self) -> list[str]:
        now = datetime.now(timezone.utc)
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT execution_id FROM execution_leases WHERE expires_at<=?", (now.isoformat(),)).fetchall()
            ids = [row[0] for row in rows]
            for execution_id in ids:
                db.execute("DELETE FROM execution_leases WHERE execution_id=?", (execution_id,))
                db.execute("UPDATE executions SET state=?, finished_at=NULL, error=?, metadata=metadata WHERE execution_id=? AND state=?", (ExecutionState.DISPATCHED.value, "worker lease expired; execution recovered", execution_id, ExecutionState.RUNNING.value))
            db.commit()
        return ids
