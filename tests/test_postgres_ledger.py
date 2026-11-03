import os
from uuid import uuid4

import pytest

from packages.runtime.src.engine import RuntimeEngine
from packages.runtime.src.ledger import PostgresEventLedger


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is required for PostgreSQL integration tests")


def test_postgres_ledger_survives_engine_restart():
    dsn = os.environ["DATABASE_URL"]
    tenant_id = "tenant-restart-" + uuid4().hex
    event = {
        "id": "evt_restart_" + uuid4().hex,
        "type": "workflow.requested",
        "tenant_id": tenant_id,
        "workflow": "durable",
        "payload": {"x": 1},
        "timestamp": "2026-09-06T00:00:00+00:00",
    }
    first = RuntimeEngine(ledger=PostgresEventLedger(dsn))
    first.execute(event)

    second = RuntimeEngine(ledger=PostgresEventLedger(dsn))
    assert second.get(event["id"]) == event
    assert second.execute({**event, "timestamp": "2026-09-06T00:01:00+00:00"})["idempotent"] is True


def test_postgres_ledger_tenant_snapshot():
    ledger = PostgresEventLedger(os.environ["DATABASE_URL"])
    tenant_id = "tenant-snapshot-" + uuid4().hex
    event_a = "evt_a_" + uuid4().hex
    event_b = "evt_b_" + uuid4().hex
    ledger.append({"id": event_a, "type": "test", "tenant_id": tenant_id, "timestamp": "2026-09-06T00:00:00+00:00"})
    ledger.append({"id": event_b, "type": "test", "tenant_id": tenant_id + "-other", "timestamp": "2026-09-06T00:00:01+00:00"})
    assert set(ledger.tenant_snapshot(tenant_id)) == {event_a}

class _SynchronizedLedger:
    """Force both PostgreSQL writers to observe the initial missing row."""

    def __init__(self, ledger, barrier):
        from threading import local

        self.ledger = ledger
        self.barrier = barrier
        self.local = local()

    def get(self, event_id):
        if not getattr(self.local, "initial_read_done", False):
            result = self.ledger.get(event_id)
            self.local.initial_read_done = True
            self.barrier.wait(timeout=10)
            return result
        return self.ledger.get(event_id)

    def append(self, event):
        return self.ledger.append(event)


def _run_two_postgres_writers(event_a, event_b):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    dsn = os.environ["DATABASE_URL"]
    barrier = Barrier(2)
    engines = [
        RuntimeEngine(ledger=_SynchronizedLedger(PostgresEventLedger(dsn), barrier))
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(engine.execute, event)
            for engine, event in zip(engines, (event_a, event_b))
        ]
        return [future.result(timeout=20) for future in futures]


def test_postgres_concurrent_identical_event_is_idempotent():
    tenant_id = f"tenant-race-identical-{uuid4().hex}"
    event_id = f"evt-race-identical-{uuid4().hex}"
    base = {
        "id": event_id,
        "type": "workflow.requested",
        "tenant_id": tenant_id,
        "workflow": "concurrent-identical",
        "payload": {"value": 1},
    }
    results = _run_two_postgres_writers(
        {**base, "timestamp": "2026-11-03T00:00:00+00:00"},
        {**base, "timestamp": "2026-11-03T00:00:01+00:00"},
    )
    assert sorted(result.get("idempotent", False) for result in results) == [False, True]
    assert all(result["status"] == "accepted" for result in results)
    stored = PostgresEventLedger(os.environ["DATABASE_URL"]).get(event_id)
    assert stored is not None
    assert stored["tenant_id"] == tenant_id


def test_postgres_concurrent_conflicting_event_rejects_loser():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    tenant_id = f"tenant-race-conflict-{uuid4().hex}"
    event_id = f"evt-race-conflict-{uuid4().hex}"
    base = {
        "id": event_id,
        "type": "workflow.requested",
        "tenant_id": tenant_id,
        "workflow": "concurrent-conflict",
    }
    events = (
        {**base, "payload": {"value": 1}, "timestamp": "2026-11-03T00:00:00+00:00"},
        {**base, "payload": {"value": 2}, "timestamp": "2026-11-03T00:00:01+00:00"},
    )
    dsn = os.environ["DATABASE_URL"]
    barrier = Barrier(2)
    engines = [
        RuntimeEngine(ledger=_SynchronizedLedger(PostgresEventLedger(dsn), barrier))
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(engine.execute, event)
            for engine, event in zip(engines, events)
        ]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result(timeout=20))
        except ValueError as exc:
            outcomes.append(exc)
    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert sum(
        isinstance(outcome, dict) and outcome["status"] == "accepted"
        for outcome in outcomes
    ) == 1
    stored = PostgresEventLedger(dsn).get(event_id)
    assert stored is not None
    assert stored["payload"] in ({"value": 1}, {"value": 2})
