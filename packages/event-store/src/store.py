from __future__ import annotations

from dataclasses import dataclass
import json
from threading import RLock
from typing import Any, Iterable

from .events import EventEnvelope, event_hash, validate_event_chain


@dataclass(frozen=True, slots=True)
class AppendResult:
    event: EventEnvelope
    inserted: bool


class EventStore:
    """Authoritative event-store interface."""

    def append(self, event: EventEnvelope) -> AppendResult:
        raise NotImplementedError

    def read(self, tenant_id: str, aggregate_id: str, run_id: str) -> tuple[EventEnvelope, ...]:
        raise NotImplementedError

    def get_event(self, event_id: str) -> EventEnvelope:
        raise NotImplementedError


class PostgresEventStore(EventStore):
    """PostgreSQL authoritative event store."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._lock = RLock()

    def append(self, event: EventEnvelope) -> AppendResult:
        if event_hash(event) != event.event_hash:
            raise ValueError("event hash does not match canonical event")

        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{event.tenant_id}\x1f{event.aggregate_id}\x1f{event.run_id}",),
            )
            cursor.execute(
                """
                SELECT event_id, event_hash, sequence, tenant_id, aggregate_id, run_id
                FROM tinyd_events WHERE event_id = %s FOR UPDATE
                """,
                (event.event_id,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if existing[1] != event.event_hash:
                    self._connection.rollback()
                    raise ValueError("event_id already exists with different event content")
                if (existing[2], existing[3], existing[4], existing[5]) != (
                    event.sequence, event.tenant_id, event.aggregate_id, event.run_id
                ):
                    self._connection.rollback()
                    raise ValueError("event_id already exists with conflicting event identity")
                self._connection.commit()
                return AppendResult(event=event, inserted=False)

            cursor.execute(
                """
                SELECT event_hash, sequence FROM tinyd_events
                WHERE tenant_id = %s AND aggregate_id = %s AND run_id = %s
                ORDER BY sequence DESC LIMIT 1 FOR UPDATE
                """,
                (event.tenant_id, event.aggregate_id, event.run_id),
            )
            previous = cursor.fetchone()
            if previous is None:
                if event.sequence != 0 or event.previous_hash is not None:
                    self._connection.rollback()
                    raise ValueError("first event must start at sequence 0 without previous_hash")
            else:
                previous_hash, previous_sequence = previous
                if event.sequence != previous_sequence + 1:
                    self._connection.rollback()
                    raise ValueError("event sequence is not contiguous")
                if event.previous_hash != previous_hash:
                    self._connection.rollback()
                    raise ValueError("event previous_hash does not match chain head")

            cursor.execute(
                """
                INSERT INTO tinyd_events (
                    event_id, event_type, schema_version, aggregate_id, run_id,
                    tenant_id, sequence, logical_time, causation_id, correlation_id,
                    producer, payload, previous_hash, event_hash, metadata, timestamp
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s)
                """,
                (
                    event.event_id, event.event_type, event.schema_version,
                    event.aggregate_id, event.run_id, event.tenant_id,
                    event.sequence, event.logical_time, event.causation_id,
                    event.correlation_id, event.producer,
                    json.dumps(dict(event.payload), sort_keys=True, separators=(",", ":")),
                    event.previous_hash, event.event_hash,
                    json.dumps(dict(event.metadata), sort_keys=True, separators=(",", ":")),
                    event.timestamp,
                ),
            )
            self._connection.commit()
            return AppendResult(event=event, inserted=True)

    def read(self, tenant_id: str, aggregate_id: str, run_id: str) -> tuple[EventEnvelope, ...]:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_id, event_type, schema_version, aggregate_id, run_id,
                       tenant_id, sequence, logical_time, causation_id, correlation_id,
                       producer, payload, previous_hash, event_hash, metadata, timestamp
                FROM tinyd_events
                WHERE tenant_id = %s AND aggregate_id = %s AND run_id = %s
                ORDER BY sequence ASC
                """,
                (tenant_id, aggregate_id, run_id),
            )
            events = tuple(_row_to_event(row) for row in cursor.fetchall())
        validate_event_chain(events)
        return events

    def get_event(self, event_id: str) -> EventEnvelope:
        if not event_id:
            raise ValueError("event_id must not be empty")
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant_id, aggregate_id, run_id
                FROM tinyd_events
                WHERE event_id = %s
                """,
                (event_id,),
            )
            identity = cursor.fetchone()
        if identity is None:
            raise KeyError(f"event not found: {event_id}")
        try:
            events = self.read(identity[0], identity[1], identity[2])
        except ValueError as exc:
            raise ValueError(f"authoritative event verification failed for {event_id}: {exc}") from exc
        for event in events:
            if event.event_id == event_id:
                return event
        raise KeyError(f"event disappeared during authoritative lookup: {event_id}")


DDL = """
CREATE TABLE IF NOT EXISTS tinyd_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence >= 0),
    logical_time BIGINT NOT NULL CHECK (logical_time >= 0),
    causation_id TEXT,
    correlation_id TEXT NOT NULL,
    producer TEXT NOT NULL,
    payload JSONB NOT NULL,
    previous_hash CHAR(64),
    event_hash CHAR(64) NOT NULL,
    metadata JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    CONSTRAINT tinyd_events_chain_identity UNIQUE (tenant_id, aggregate_id, run_id, sequence),
    CONSTRAINT tinyd_events_event_hash_unique UNIQUE (event_hash)
);
CREATE INDEX IF NOT EXISTS tinyd_events_stream_idx
    ON tinyd_events (tenant_id, aggregate_id, run_id, sequence);
"""


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("PostgreSQL JSONB field is not an object")
    return value


def _row_to_event(row: Iterable[Any]) -> EventEnvelope:
    values = tuple(row)
    if len(values) != 16:
        raise ValueError("invalid tinyd_events row")
    return EventEnvelope(
        event_id=values[0], event_type=values[1], schema_version=values[2],
        aggregate_id=values[3], run_id=values[4], tenant_id=values[5],
        sequence=values[6], logical_time=values[7], causation_id=values[8],
        correlation_id=values[9], producer=values[10], payload=_json_object(values[11]),
        previous_hash=values[12], event_hash=values[13], metadata=_json_object(values[14]),
        timestamp=values[15].isoformat() if hasattr(values[15], "isoformat") else values[15],
    )
