from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row


class PostgresEventLedger:
    """Durable append-only event ledger backed by PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn
        self.initialize()

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tinyd_events (
                    event_id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    event_type TEXT NOT NULL,
                    event JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS tinyd_events_tenant_created_idx ON tinyd_events (tenant_id, created_at, event_id)")

    def append(self, event: dict[str, Any]) -> bool:
        event_id = event["id"]
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO tinyd_events (event_id, tenant_id, event_type, event)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                (event_id, event.get("tenant_id"), event.get("type", "unknown"), json.dumps(event, sort_keys=True, separators=(",", ":"))),
            ).fetchone()
            return row is not None

    def get(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT event FROM tinyd_events WHERE event_id = %s", (event_id,)).fetchone()
            return dict(row["event"]) if row else None

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT event_id, event FROM tinyd_events ORDER BY created_at, event_id").fetchall()
            return {row["event_id"]: dict(row["event"]) for row in rows}

    def tenant_snapshot(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT event_id, event FROM tinyd_events WHERE tenant_id = %s ORDER BY created_at, event_id", (tenant_id,)).fetchall()
            return {row["event_id"]: dict(row["event"]) for row in rows}
