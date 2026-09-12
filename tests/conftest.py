import os

import pytest

from apps.api.main import engine


@pytest.fixture(autouse=True)
def isolate_runtime_state():
    """Reset the authoritative test store before every test."""
    engine.state.clear()
    if engine.ledger is not None:
        with engine.ledger._connect() as conn:
            conn.execute("DELETE FROM tinyd_events")
    os.environ.pop("TINYD_TENANT_TOKENS", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
    yield
    engine.state.clear()
