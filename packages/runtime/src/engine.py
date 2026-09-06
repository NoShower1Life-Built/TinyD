from dataclasses import dataclass, field
from typing import Any

from packages.runtime.src.ledger import PostgresEventLedger


@dataclass
class RuntimeEngine:
    """Deterministic runtime with durable PostgreSQL persistence when configured."""

    ledger: PostgresEventLedger | None = None
    state: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _semantic_event(event: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in event.items() if key != "timestamp"}

    def execute(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event id is required")
        existing = self.get(event_id)
        if existing is None:
            if self.ledger is not None:
                self.ledger.append(event)
            self.state[event_id] = dict(event)
            return {"status": "accepted", "event_id": event_id}
        if self._semantic_event(existing) != self._semantic_event(event):
            raise ValueError(f"event id collision: {event_id}")
        return {"status": "accepted", "event_id": event_id, "idempotent": True}

    def get(self, event_id: str) -> dict[str, Any] | None:
        if self.ledger is not None:
            return self.ledger.get(event_id)
        event = self.state.get(event_id)
        return dict(event) if event is not None else None

    def snapshot(self) -> dict[str, Any]:
        if self.ledger is not None:
            return self.ledger.snapshot()
        return {event_id: dict(event) for event_id, event in self.state.items()}

    def tenant_snapshot(self, tenant_id: str) -> dict[str, Any]:
        if self.ledger is not None:
            return self.ledger.tenant_snapshot(tenant_id)
        return {event_id: dict(event) for event_id, event in self.state.items() if event.get("tenant_id") == tenant_id}
