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

    def _assert_same_event(self, existing: dict[str, Any], event: dict[str, Any]) -> None:
        if self._semantic_event(existing) != self._semantic_event(event):
            raise ValueError(f"event id collision: {event['id']}")

    def execute(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event id is required")

        existing = self.get(event_id)
        if existing is not None:
            self._assert_same_event(existing, event)
            return {"status": "accepted", "event_id": event_id, "idempotent": True}

        if self.ledger is not None:
            inserted = self.ledger.append(event)
            if not inserted:
                # A concurrent worker may have inserted the key after the initial read.
                persisted = self.ledger.get(event_id)
                if persisted is None:
                    raise RuntimeError("event insert conflicted but the persisted event could not be read")
                self._assert_same_event(persisted, event)
                return {"status": "accepted", "event_id": event_id, "idempotent": True}

        self.state[event_id] = dict(event)
        return {"status": "accepted", "event_id": event_id}
