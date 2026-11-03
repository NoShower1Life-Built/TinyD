import os
from uuid import uuid4

import pytest

from packages.runtime.src.engine import RuntimeEngine
from packages.runtime.src.ledger import PostgresEventLedger


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is required for PostgreSQL integration tests")


def test_postgres_ledger_survives_engine_restart():
    dsn = os.environ["DATABASE_URL"]
    tenant_id = f"tenant-pg-{uuid4().hex}"
    event_id = f"evt-pg-restart-{uuid4().hex}"
    first = RuntimeEngine(ledger=PostgresEventLedger(dsn))
    event = {"id": event_id, "type": "workflow.requested", "tenant_id": tenant_id, "workflow": "durable", "payload": {"x": 1}, "timestamp": "2026-09-06T00:00:00+00:00"}
    first.execute(event)

    second = RuntimeEngine(ledger=PostgresEventLedger(dsn))
    assert second.get(event["id"]) == event
    assert second.execute({**event, "timestamp": "2026-09-06T00:01:00+00:00"})["idempotent"] is True


def test_postgres_ledger_tenant_snapshot():
    ledger = PostgresEventLedger(os.environ["DATABASE_URL"])
    tenant_a = f"tenant-a-{uuid4().hex}"
    tenant_b = f"tenant-b-{uuid4().hex}"
    event_a = f"evt-pg-a-{uuid4().hex}"
    event_b = f"evt-pg-b-{uuid4().hex}"
    ledger.append({"id": event_a, "type": "test", "tenant_id": tenant_a, "timestamp": "2026-09-06T00:00:00+00:00"})
    ledger.append({"id": event_b, "type": "test", "tenant_id": tenant_b, "timestamp": "2026-09-06T00:00:01+00:00"})
    assert set(ledger.tenant_snapshot(tenant_a)) == {event_a}
