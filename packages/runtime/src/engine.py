from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeEngine:
    """Minimal deterministic execution runtime foundation."""

    state: dict[str, Any] = field(default_factory=dict)

    def execute(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = event.get("id")
        self.state[event_id] = event
        return {"status": "accepted", "event_id": event_id}

    def snapshot(self) -> dict[str, Any]:
        return dict(self.state)
