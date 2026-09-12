from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from packages.contracts.src.envelope import EventEnvelope


class EventJournalError(RuntimeError):
    """Base error for authoritative event-journal failures."""


class EventSequenceConflict(EventJournalError):
    """The supplied aggregate sequence is not the next authoritative sequence."""


class EventIntegrityError(EventJournalError):
    """The supplied event integrity chain or digest is invalid."""


class EventTenantError(EventJournalError):
    """The event cannot be accepted without valid tenant ownership."""


class PostgresEventJournal:
    """Authoritative append-only event history for TinyD.

    The journal owns aggregate sequencing and integrity-chain validation. A
    successful append commits the event and aggregate head in one PostgreSQL
    transaction. Consumers must treat this journal as the source of truth for
    durable event history; in-memory state is not an authoritative substitute.
    """

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn
        self.initialize()

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tinyd_event_journal (
                    event_id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    event_type TEXT NOT NULL,
                    event_version INTEGER NOT NULL CHECK (event_version >= 1),
                    occurred_at TIMESTAMPTZ NOT NULL,
                    agent_id UUID NOT NULL,
                    conversation_id UUID,
                    run_id UUID,
                    task_id UUID,
                    step_id UUID,
                    correlation_id UUID NOT NULL,
                    causation_id UUID,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id UUID NOT NULL,
                    sequence BIGINT NOT NULL CHECK (sequence >= 1),
                    producer TEXT NOT NULL,
                    event JSONB NOT NULL,
                    previous_digest TEXT,
                    digest TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (tenant_id, aggregate_type, aggregate_id, sequence),
                    UNIQUE (tenant_id, event_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tinyd_event_journal_heads (
                    tenant_id UUID NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id UUID NOT NULL,
                    last_sequence BIGINT NOT NULL CHECK (last_sequence >= 0),
                    last_digest TEXT,
                    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS tinyd_event_journal_tenant_created_idx
                ON tinyd_event_journal (tenant_id, created_at, event_id)
                """
            )

    @staticmethod
    def _canonical_for_digest(event: EventEnvelope, previous_digest: str | None) -> str:
        body = event.model_dump(mode="json", exclude={"integrity"})
        body["integrity"] = {"previous_digest": previous_digest}
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    @classmethod
    def calculate_digest(cls, event: EventEnvelope, previous_digest: str | None) -> str:
        canonical = cls._canonical_for_digest(event, previous_digest).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _event_from_row(row: dict[str, Any]) -> EventEnvelope:
        return EventEnvelope.model_validate(row["event"])

    def append(self, event: EventEnvelope) -> EventEnvelope:
        if not isinstance(event.tenant_id, UUID):
            raise EventTenantError("tenant_id is required")
        if event.sequence < 1:
            raise EventSequenceConflict("event sequence must be >= 1")

        with self._connect() as conn:
            with conn.transaction():
                existing = conn.execute(
                    "SELECT event FROM tinyd_event_journal WHERE event_id = %s FOR UPDATE",
                    (event.event_id,),
                ).fetchone()
                if existing is not None:
                    persisted = self._event_from_row(existing)
                    if persisted.model_dump(mode="json") != event.model_dump(mode="json"):
                        raise EventIntegrityError(f"event id collision: {event.event_id}")
                    return persisted

                conn.execute(
                    """
                    INSERT INTO tinyd_event_journal_heads
                        (tenant_id, aggregate_type, aggregate_id, last_sequence, last_digest)
                    VALUES (%s, %s, %s, 0, NULL)
                    ON CONFLICT (tenant_id, aggregate_type, aggregate_id) DO NOTHING
                    """,
                    (event.tenant_id, event.aggregate_type, event.aggregate_id),
                )
                head = conn.execute(
                    """
                    SELECT last_sequence, last_digest
                    FROM tinyd_event_journal_heads
                    WHERE tenant_id = %s AND aggregate_type = %s AND aggregate_id = %s
                    FOR UPDATE
                    """,
                    (event.tenant_id, event.aggregate_type, event.aggregate_id),
                ).fetchone()
                if head is None:
                    raise EventJournalError("aggregate head disappeared during append")

                expected_sequence = int(head["last_sequence"]) + 1
                previous_digest = head["last_digest"]
                if event.sequence != expected_sequence:
                    raise EventSequenceConflict(
                        f"expected aggregate sequence {expected_sequence}, received {event.sequence}"
                    )
                if event.integrity.previous_digest != previous_digest:
                    raise EventIntegrityError("previous digest does not match aggregate head")

                expected_digest = self.calculate_digest(event, previous_digest)
                if event.integrity.digest != expected_digest:
                    raise EventIntegrityError("event digest does not match canonical event content")

                conn.execute(
                    """
                    INSERT INTO tinyd_event_journal (
                        event_id, tenant_id, event_type, event_version, occurred_at,
                        agent_id, conversation_id, run_id, task_id, step_id,
                        correlation_id, causation_id, aggregate_type, aggregate_id,
                        sequence, producer, event, previous_digest, digest
                    ) VALUES (
                        %(event_id)s, %(tenant_id)s, %(event_type)s, %(event_version)s, %(occurred_at)s,
                        %(agent_id)s, %(conversation_id)s, %(run_id)s, %(task_id)s, %(step_id)s,
                        %(correlation_id)s, %(causation_id)s, %(aggregate_type)s, %(aggregate_id)s,
                        %(sequence)s, %(producer)s, %(event)s::jsonb, %(previous_digest)s, %(digest)s
                    )
                    """,
                    {
                        "event_id": event.event_id,
                        "tenant_id": event.tenant_id,
                        "event_type": event.event_type,
                        "event_version": event.event_version,
                        "occurred_at": event.occurred_at,
                        "agent_id": event.agent_id,
                        "conversation_id": event.conversation_id,
                        "run_id": event.run_id,
                        "task_id": event.task_id,
                        "step_id": event.step_id,
                        "correlation_id": event.correlation_id,
                        "causation_id": event.causation_id,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "sequence": event.sequence,
                        "producer": event.producer,
                        "event": json.dumps(event.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
                        "previous_digest": previous_digest,
                        "digest": expected_digest,
                    },
                )
                conn.execute(
                    """
                    UPDATE tinyd_event_journal_heads
                    SET last_sequence = %s, last_digest = %s
                    WHERE tenant_id = %s AND aggregate_type = %s AND aggregate_id = %s
                    """,
                    (
                        event.sequence,
                        expected_digest,
                        event.tenant_id,
                        event.aggregate_type,
                        event.aggregate_id,
                    ),
                )
                return event

    def get(self, event_id: UUID, tenant_id: UUID) -> EventEnvelope | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT event FROM tinyd_event_journal WHERE event_id = %s AND tenant_id = %s",
                (event_id, tenant_id),
            ).fetchone()
            return self._event_from_row(row) if row else None

    def history(self, tenant_id: UUID, aggregate_type: str, aggregate_id: UUID) -> list[EventEnvelope]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event
                FROM tinyd_event_journal
                WHERE tenant_id = %s AND aggregate_type = %s AND aggregate_id = %s
                ORDER BY sequence ASC
                """,
                (tenant_id, aggregate_type, aggregate_id),
            ).fetchall()
            return [self._event_from_row(row) for row in rows]

    def tenant_history(self, tenant_id: UUID) -> list[EventEnvelope]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event
                FROM tinyd_event_journal
                WHERE tenant_id = %s
                ORDER BY created_at ASC, event_id ASC
                """,
                (tenant_id,),
            ).fetchall()
            return [self._event_from_row(row) for row in rows]
