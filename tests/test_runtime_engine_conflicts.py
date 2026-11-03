import pytest

from packages.runtime.src.engine import RuntimeEngine


class RejectingLedger:
    """Exercise the durable insert-conflict resolution path."""

    def __init__(self, stored_event=None):
        self.stored_event = stored_event

    def get(self, event_id):
        if self.stored_event and self.stored_event["id"] == event_id:
            return dict(self.stored_event)
        return None

    def append(self, event):
        return False

    def snapshot(self):
        return {}

    def tenant_snapshot(self, tenant_id):
        return {}


def make_event(payload=None, timestamp="2026-11-03T00:00:00+00:00"):
    return {
        "id": "evt_race",
        "type": "workflow.requested",
        "tenant_id": "tenant-a",
        "workflow": "audit",
        "payload": payload if payload is not None else {"x": 1},
        "timestamp": timestamp,
    }


def test_concurrent_identical_insert_is_idempotent():
    stored = make_event()
    engine = RuntimeEngine(ledger=RejectingLedger(stored))

    result = engine.execute(make_event(timestamp="2026-11-03T00:01:00+00:00"))

    assert result == {
        "status": "accepted",
        "event_id": "evt_race",
        "idempotent": True,
    }


def test_concurrent_conflicting_insert_raises_collision():
    stored = make_event(payload={"x": 1})
    engine = RuntimeEngine(ledger=RejectingLedger(stored))

    with pytest.raises(ValueError, match="event id collision: evt_race"):
        engine.execute(make_event(payload={"x": 2}))


def test_ledger_rejection_without_stored_event_fails_closed():
    engine = RuntimeEngine(ledger=RejectingLedger())

    with pytest.raises(RuntimeError, match="persisted event could not be read"):
        engine.execute(make_event())

class FailingLedger:
    def get(self, event_id):
        return None

    def append(self, event):
        raise ConnectionError("database unavailable")


def test_database_failure_does_not_report_acceptance():
    engine = RuntimeEngine(ledger=FailingLedger())

    with pytest.raises(ConnectionError, match="database unavailable"):
        engine.execute(make_event())
