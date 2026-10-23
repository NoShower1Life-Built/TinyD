"""Shared test isolation for opt-in PostgreSQL integration runs.

Database truncation is deliberately disabled unless the CI/test runner explicitly
sets TINYD_TEST_DATABASE=1. Never point that opt-in flag at a production database.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def isolate_postgres_test_ledger():
    if os.getenv("TINYD_TEST_DATABASE") != "1":
        yield
        return

    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("TINYD_TEST_DATABASE=1 requires DATABASE_URL")

    import psycopg

    with psycopg.connect(dsn) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tinyd_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT,
                event_type TEXT NOT NULL,
                event JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("TRUNCATE TABLE tinyd_events")

    yield
