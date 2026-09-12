from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence


_HASH_LENGTH = 64
_HEX = frozenset("0123456789abcdef")


def canonical_json(value: Any) -> bytes:
    """Serialize JSON-compatible data deterministically for integrity hashing."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("value must contain only canonical JSON-compatible data") from exc
    return encoded.encode("utf-8")


def sha256_hex(value: Any) -> str:
    """Return the lowercase SHA-256 digest of canonical JSON bytes."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


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
        if not _is_hash(self.event_hash):
            raise ValueError("event_hash must be a lowercase SHA-256 hex digest")
        if self.previous_hash is not None and not _is_hash(self.previous_hash):
            raise ValueError("previous_hash must be a lowercase SHA-256 hex digest")
        canonical_json(self.payload)
        canonical_json(self.metadata)

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


def event_hash(event: EventEnvelope) -> str:
    """Compute the authoritative digest for an event envelope."""
    return sha256_hex(event.without_hash())


def verify_event_hash(event: EventEnvelope) -> None:
    """Raise ValueError when an event's stored digest is not authoritative."""
    expected = event_hash(event)
    if event.event_hash != expected:
        raise ValueError(
            f"event hash mismatch for {event.event_id}: expected {expected}, got {event.event_hash}"
        )


def validate_event_chain(events: Sequence[EventEnvelope]) -> None:
    """Validate hashes, identity continuity, sequence, logical time, and links."""
    if not events:
        return

    for index, event in enumerate(events):
        verify_event_hash(event)
        if index == 0:
            if event.sequence != 0:
                raise ValueError("event chain must start at sequence 0")
            if event.previous_hash is not None:
                raise ValueError("first event must not have a previous_hash")
            continue

        previous = events[index - 1]
        if event.tenant_id != previous.tenant_id:
            raise ValueError("event chain tenant_id changed")
        if event.aggregate_id != previous.aggregate_id:
            raise ValueError("event chain aggregate_id changed")
        if event.run_id != previous.run_id:
            raise ValueError("event chain run_id changed")
        if event.sequence != previous.sequence + 1:
            raise ValueError("event sequence is not contiguous")
        if event.previous_hash != previous.event_hash:
            raise ValueError("event previous_hash does not match predecessor")
        if event.logical_time < previous.logical_time:
            raise ValueError("event logical_time moved backwards")


def _is_hash(value: str) -> bool:
    return len(value) == _HASH_LENGTH and all(char in _HEX for char in value)
