from typing import Any

import pytest

from packages.runtime.src.engine import RuntimeEngine


class RacingLedger:
    """Represent a concurrent insert between the engine's read and append."""

    def __init__(self, durable_event: dict[str, Any]) -> None:
        self.durable_event = dict(durable_event)
        self.reads = 0

    def get(self, event_id: str) -> dict[str, Any] | None:
        self.reads += 1
        if self.reads == 1:
            return None
        if self.durable_event["id"] == event_id:
            return dict(self.durable_event)
        return None

    def append(self, event: dict[str, Any]) -> bool:
        return False

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {self.durable_event["id"]: dict(self.durable_event)}

    def tenant_snapshot(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        if self.durable_event.get("tenant_id") == tenant_id:
            return {self.durable_event["id"]: dict(self.durable_event)}
        return {}


def test_concurrent_duplicate_insert_returns_idempotent_result() -> None:
    durable = {
        "id": "evt-same",
        "type": "workflow.requested",
        "tenant_id": "tenant-a",
        "payload": {"amount": 7},
        "timestamp": "2026-10-22T00:00:00Z",
    }
    ledger = RacingLedger(durable)
    engine = RuntimeEngine(ledger=ledger)  # type: ignore[arg-type]
    retry = {**durable, "timestamp": "2026-10-22T00:00:01Z"}

    result = engine.execute(retry)

    assert result == {
        "status": "accepted",
        "event_id": "evt-same",
        "idempotent": True,
    }
    assert engine.get("evt-same") == durable


def test_concurrent_event_id_collision_is_rejected() -> None:
    durable = {
        "id": "evt-same",
        "type": "workflow.requested",
        "tenant_id": "tenant-a",
        "payload": {"amount": 7},
        "timestamp": "2026-10-22T00:00:00Z",
    }
    ledger = RacingLedger(durable)
    engine = RuntimeEngine(ledger=ledger)  # type: ignore[arg-type]
    conflicting = {**durable, "payload": {"amount": 999}}

    with pytest.raises(ValueError, match="event id collision"):
        engine.execute(conflicting)
