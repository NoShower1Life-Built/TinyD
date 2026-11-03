"""Explicit, isolated PostgreSQL cleanup for CI integration tests.

This fixture is deliberately opt-in. It refuses to truncate a database unless
the caller sets TINYD_TEST_DB_RESET=1; CI sets it only for ephemeral service
containers created for this workflow.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def isolate_ephemeral_postgres_database():
    if os.getenv("TINYD_TEST_DB_RESET") != "1":
        yield
        return

    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("TINYD_TEST_DB_RESET=1 requires DATABASE_URL")

    from urllib.parse import urlparse

    database_name = urlparse(dsn).path.lstrip("/")
    if database_name != "tinyd":
        raise RuntimeError(
            "refusing destructive test cleanup: expected isolated database 'tinyd'"
        )

    import psycopg

    with psycopg.connect(dsn) as conn:
        conn.execute("TRUNCATE TABLE tinyd_events")
        journal_exists = conn.execute(
            "SELECT to_regclass('public.tinyd_event_journal')"
        ).fetchone()[0]
        if journal_exists:
            worker_tasks_exists = conn.execute(
                "SELECT to_regclass('public.tinyd_worker_tasks')"
            ).fetchone()[0]
            if worker_tasks_exists:
                conn.execute("TRUNCATE TABLE tinyd_worker_tasks")
            conn.execute(
                "TRUNCATE TABLE tinyd_event_journal, tinyd_event_journal_heads"
            )

    # API tests share a module-level engine; reset its process-local cache too.
    try:
        from apps.api.main import engine
    except (ImportError, RuntimeError):
        pass
    else:
        engine.state.clear()

    yield
