from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from packages.contracts.src.envelope import EventEnvelope, EventIntegrity
from packages.runtime.src.journal import (
    EventIntegrityError,
    EventSequenceConflict,
    PostgresEventJournal,
)


def append_tenant_event(
    journal: PostgresEventJournal,
    *,
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
    event_id: UUID | None = None,
    agent_id: UUID | None = None,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    producer: str = "tinyd-control-plane",
    max_attempts: int = 8,
) -> EventEnvelope:
    """Append an event at the next aggregate sequence with server-computed integrity.

    The journal remains the authority for sequence validation and digest checking.
    Concurrent appenders may race while reading the head; sequence conflicts are
    retried. Reusing an event ID is idempotent only when its semantic content
    matches the persisted event.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    event_id = event_id or uuid4()
    agent_id = agent_id or uuid4()
    correlation_id = correlation_id or event_id

    existing = journal.get(event_id, tenant_id)
    if existing is not None:
        expected = {
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": payload,
        }
        actual = {
            "event_type": existing.event_type,
            "aggregate_type": existing.aggregate_type,
            "aggregate_id": existing.aggregate_id,
            "payload": existing.payload,
        }
        if actual != expected:
            raise EventIntegrityError(f"event id collision: {event_id}")
        return existing

    for _ in range(max_attempts):
        history = journal.history(tenant_id, aggregate_type, aggregate_id)
        previous = history[-1] if history else None
        sequence = (previous.sequence + 1) if previous else 1
        previous_digest = previous.integrity.digest if previous else None
        candidate = EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            agent_id=agent_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence=sequence,
            producer=producer,
            payload=payload,
            integrity=EventIntegrity(previous_digest=previous_digest, digest=""),
        )
        digest = journal.calculate_digest(candidate, previous_digest)
        candidate = candidate.model_copy(
            update={
                "integrity": EventIntegrity(
                    previous_digest=previous_digest,
                    digest=digest,
                )
            }
        )
        try:
            return journal.append(candidate)
        except EventSequenceConflict:
            existing = journal.get(event_id, tenant_id)
            if existing is not None:
                expected = {
                    "event_type": event_type,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "payload": payload,
                }
                actual = {
                    "event_type": existing.event_type,
                    "aggregate_type": existing.aggregate_type,
                    "aggregate_id": existing.aggregate_id,
                    "payload": existing.payload,
                }
                if actual != expected:
                    raise EventIntegrityError(f"event id collision: {event_id}")
                return existing
            continue
    raise EventSequenceConflict(
        f"could not append event after {max_attempts} concurrent sequence conflicts"
    )
