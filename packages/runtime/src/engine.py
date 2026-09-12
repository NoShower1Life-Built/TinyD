from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .event_journal import EventJournal


@dataclass
class RuntimeEngine:
    """Deterministic runtime whose authoritative state boundary is the journal."""

    journal: EventJournal

    def execute(self, event: Any) -> dict[str, Any]:
        result = self.journal.append(event)
        return {
            "status": "accepted" if result.inserted else "already_recorded",
            "event_id": event.event_id,
            "inserted": result.inserted,
        }

    def load_stream(self, tenant_id: str, aggregate_id: str, run_id: str) -> tuple[Any, ...]:
        return self.journal.load(tenant_id, aggregate_id, run_id)
