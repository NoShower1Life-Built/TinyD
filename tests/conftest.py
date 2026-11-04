import os

import pytest

from apps.api.main import engine


@pytest.fixture(autouse=True)
def isolate_runtime_state():
    """Reset test state; PostgreSQL cleanup requires explicit test authorization."""
    engine.state.clear()
    if engine.ledger is not None:
        if os.getenv("TINYD_ALLOW_DESTRUCTIVE_TEST_DB_CLEANUP") != "1":
            raise RuntimeError(
                "refusing PostgreSQL cleanup without explicit test-environment authorization"
            )
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("PostgreSQL ledger is configured but DATABASE_URL is unset")
        with engine.ledger._connect() as conn:
            conn.execute("DELETE FROM tinyd_events")
    os.environ.pop("TINYD_TENANT_TOKENS", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
    yield
    engine.state.clear()
