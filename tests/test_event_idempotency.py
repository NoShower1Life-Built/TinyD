from __future__ import annotations

import pytest

from packages.runtime.src.engine import RuntimeEngine


class ConflictLedger:
    """Minimal ledger fake for the insert-conflict path."""

    def __init__(self, stored_event):
        self.stored_event = stored_event
        self.append_calls = 0

    def get(self, event_id):
        if self.stored_event and self.stored_event["id"] == event_id:
            return dict(self.stored_event)
        return None

    def append(self, event):
        self.append_calls += 1
        return False


def event(**overrides):
    value = {
        "id": "evt_concurrent",
        "type": "workflow.requested",
        "tenant_id": "tenant-a",
        "workflow": "run",
        "payload": {"x": 1},
        "timestamp": "2026-10-22T00:00:00+00:00",
    }
    value.update(overrides)
    return value


def test_insert_conflict_with_matching_event_is_idempotent():
    stored = event()
    ledger = ConflictLedger(stored)
    engine = RuntimeEngine(ledger=ledger)

    result = engine.execute(event(timestamp="2026-10-22T00:01:00+00:00"))

    assert result == {
        "status": "accepted",
        "event_id": "evt_concurrent",
        "idempotent": True,
    }
    assert ledger.append_calls == 1


def test_insert_conflict_with_different_payload_is_rejected():
    ledger = ConflictLedger(event(payload={"x": 1}))
    engine = RuntimeEngine(ledger=ledger)

    with pytest.raises(ValueError, match="event id collision: evt_concurrent"):
        engine.execute(event(payload={"x": 2}))


def test_insert_conflict_without_durable_winner_is_rejected():
    ledger = ConflictLedger(None)
    engine = RuntimeEngine(ledger=ledger)

    with pytest.raises(RuntimeError, match="event insert conflicted but no durable event exists"):
        engine.execute(event())


class FailingLedger:
    def get(self, event_id):
        return None

    def append(self, event):
        raise ConnectionError("database unavailable")


def test_database_failure_does_not_report_acceptance():
    engine = RuntimeEngine(ledger=FailingLedger())

    with pytest.raises(ConnectionError, match="database unavailable"):
        engine.execute(event())
