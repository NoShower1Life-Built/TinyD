from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Canonical immutable TinyD event envelope.

    ``event_hash`` is the SHA-256 digest of the canonical event representation
    excluding ``event_hash`` itself. ``previous_hash`` links this event to the
    preceding event in its authoritative sequence.
    """

    event_id: str
    event_type: str
    schema_version: str
    aggregate_id: str
    run_id: str
    tenant_id: str
    sequence: int
    logical_time: int
    causation_id: str | None
    correlation_id: str
    producer: str
    payload: Mapping[str, Any]
    previous_hash: str | None
    event_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        required = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_id": self.aggregate_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "producer": self.producer,
            "event_hash": self.event_hash,
        }
        for name, value in required.items():
            if not value:
                raise ValueError(f"{name} is required")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.logical_time < 0:
            raise ValueError("logical_time must be non-negative")

    def without_hash(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_id": self.aggregate_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "sequence": self.sequence,
            "logical_time": self.logical_time,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "producer": self.producer,
            "payload": dict(self.payload),
            "previous_hash": self.previous_hash,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }

    def as_dict(self) -> dict[str, Any]:
        result = self.without_hash()
        result["event_hash"] = self.event_hash
        return result
