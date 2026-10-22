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


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import uuid4


class FirstReadBarrierLedger:
    """Synchronize first reads so concurrent engines both observe a missing ID."""

    def __init__(self, dsn: str, barrier: Barrier):
        self.ledger = PostgresEventLedger(dsn)
        self.barrier = barrier
        self._lock = Lock()
        self._first_read = True

    def get(self, event_id):
        result = self.ledger.get(event_id)
        wait = False
        with self._lock:
            if self._first_read:
                self._first_read = False
                wait = True
        if wait:
            self.barrier.wait(timeout=10)
        return result

    def append(self, event):
        return self.ledger.append(event)

    def snapshot(self):
        return self.ledger.snapshot()

    def tenant_snapshot(self, tenant_id):
        return self.ledger.tenant_snapshot(tenant_id)


def test_concurrent_identical_events_are_accepted_idempotently():
    dsn = os.environ["DATABASE_URL"]
    event_id = f"evt_concurrent_identical_{uuid4().hex}"
    event = {
        "id": event_id,
        "type": "workflow.requested",
        "tenant_id": "tenant-concurrency",
        "workflow": "concurrent",
        "payload": {"value": 1},
        "timestamp": "2026-10-22T00:00:00+00:00",
    }
    barrier = Barrier(2)

    def submit():
        engine = RuntimeEngine(ledger=FirstReadBarrierLedger(dsn, barrier))
        return engine.execute(dict(event))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))

    assert len(results) == 2
    assert all(result["status"] == "accepted" for result in results)
    assert sorted(result.get("idempotent", False) for result in results) == [False, True]
    assert PostgresEventLedger(dsn).get(event_id) == event


def test_concurrent_conflicting_events_cannot_both_be_accepted():
    dsn = os.environ["DATABASE_URL"]
    event_id = f"evt_concurrent_conflict_{uuid4().hex}"
    base = {
        "id": event_id,
        "type": "workflow.requested",
        "tenant_id": "tenant-concurrency",
        "workflow": "concurrent",
        "payload": {"value": 1},
        "timestamp": "2026-10-22T00:00:00+00:00",
    }
    variants = [base, {**base, "payload": {"value": 2}}]
    barrier = Barrier(2)

    def submit(event):
        engine = RuntimeEngine(ledger=FirstReadBarrierLedger(dsn, barrier))
        try:
            return engine.execute(event)
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, variants))

    accepted = [result for result in results if isinstance(result, dict)]
    rejected = [result for result in results if isinstance(result, ValueError)]
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert "event id collision" in str(rejected[0])
    assert PostgresEventLedger(dsn).get(event_id) in variants
