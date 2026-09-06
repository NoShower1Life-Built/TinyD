import os

import pytest

from packages.runtime.src.engine import RuntimeEngine
from packages.runtime.src.ledger import PostgresEventLedger


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is required for PostgreSQL integration tests")


def test_postgres_ledger_survives_engine_restart():
    dsn = os.environ["DATABASE_URL"]
    first = RuntimeEngine(ledger=PostgresEventLedger(dsn))
    event = {"id": "evt_pg_restart", "type": "workflow.requested", "tenant_id": "tenant-pg", "workflow": "durable", "payload": {"x": 1}, "timestamp": "2026-09-06T00:00:00+00:00"}
    first.execute(event)

    second = RuntimeEngine(ledger=PostgresEventLedger(dsn))
    assert second.get(event["id"]) == event
    assert second.execute({**event, "timestamp": "2026-09-06T00:01:00+00:00"})["idempotent"] is True


def test_postgres_ledger_tenant_snapshot():
    ledger = PostgresEventLedger(os.environ["DATABASE_URL"])
    ledger.append({"id": "evt_pg_tenant_a", "type": "test", "tenant_id": "tenant-a", "timestamp": "2026-09-06T00:00:00+00:00"})
    ledger.append({"id": "evt_pg_tenant_b", "type": "test", "tenant_id": "tenant-b", "timestamp": "2026-09-06T00:00:01+00:00"})
    assert set(ledger.tenant_snapshot("tenant-a")) == {"evt_pg_tenant_a"}
