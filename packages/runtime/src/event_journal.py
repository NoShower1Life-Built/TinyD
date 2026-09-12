from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class EventStorePort(Protocol):
    def append(self, event: Any) -> Any: ...
    def read(self, tenant_id: str, aggregate_id: str, run_id: str) -> tuple[Any, ...]: ...
    def get_event(self, event_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class EventJournal:
    """Runtime boundary over the authoritative event store.

    Runtime state is derived from the journal; the journal itself is never
    replaced by an in-memory event list.
    """

    store: EventStorePort

    def append(self, event: Any) -> Any:
        return self.store.append(event)

    def load(self, tenant_id: str, aggregate_id: str, run_id: str) -> tuple[Any, ...]:
        return self.store.read(tenant_id, aggregate_id, run_id)

    def load_event(self, event_id: str) -> Any:
        return self.store.get_event(event_id)
