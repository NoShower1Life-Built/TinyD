from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeEngine:
    """Deterministic in-memory runtime foundation with immutable event records."""

    state: dict[str, Any] = field(default_factory=dict)

    def execute(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event id is required")
        existing = self.state.get(event_id)
        if existing is None:
            self.state[event_id] = dict(event)
            return {"status": "accepted", "event_id": event_id}
        if existing != event:
            raise ValueError(f"event id collision: {event_id}")
        return {"status": "accepted", "event_id": event_id, "idempotent": True}

    def snapshot(self) -> dict[str, Any]:
        return {event_id: dict(event) for event_id, event in self.state.items()}
