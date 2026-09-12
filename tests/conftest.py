import os

import pytest

from apps.api.main import engine


@pytest.fixture(autouse=True)
def isolate_runtime_state():
    """Reset test state without allowing destructive cleanup of a non-test database."""
    engine.state.clear()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if engine.ledger is not None:
        if not database_url:
            raise RuntimeError("PostgreSQL ledger is configured but DATABASE_URL is unset")
        normalized = database_url.lower()
        if "test" not in normalized:
            raise RuntimeError("refusing PostgreSQL cleanup unless DATABASE_URL identifies a test database")
        with engine.ledger._connect() as conn:
            conn.execute("DELETE FROM tinyd_events")
    os.environ.pop("TINYD_TENANT_TOKENS", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
    yield
    engine.state.clear()
