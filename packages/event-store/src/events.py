from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: str
    payload: dict
    timestamp: str = datetime.now(timezone.utc).isoformat()
