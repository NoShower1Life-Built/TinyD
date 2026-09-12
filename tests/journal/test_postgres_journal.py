import os
from uuid import uuid4

import psycopg
import pytest

from packages.contracts.src.envelope import EventEnvelope, EventIntegrity
from packages.runtime.src.journal import (
    EventIntegrityError,
    EventSequenceConflict,
    PostgresEventJournal,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="PostgreSQL integration tests require DATABASE_URL"
)


@pytest.fixture
def journal() -> PostgresEventJournal:
    instance = PostgresEventJournal(os.environ["DATABASE_URL"])
    with instance._connect() as conn:
        conn.execute("DELETE FROM tinyd_event_journal")
        conn.execute("DELETE FROM tinyd_event_journal_heads")
    return instance


def make_event(journal: PostgresEventJournal, *, tenant_id, aggregate_id, sequence, previous_digest=None):
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="run.requested",
        event_version=1,
        tenant_id=tenant_id,
        agent_id=uuid4(),
        correlation_id=uuid4(),
        aggregate_type="run",
        aggregate_id=aggregate_id,
        sequence=sequence,
        producer="tinyd-agent",
        payload={"intent": "test", "sequence": sequence},
        integrity=EventIntegrity(previous_digest=previous_digest, digest="pending"),
    )
    digest = journal.calculate_digest(event, previous_digest)
    return event.model_copy(update={"integrity": EventIntegrity(previous_digest=previous_digest, digest=digest)})


def test_append_assigns_authoritative_history_and_preserves_chain(journal):
    tenant_id = uuid4()
    aggregate_id = uuid4()

    first = make_event(journal, tenant_id=tenant_id, aggregate_id=aggregate_id, sequence=1)
    persisted_first = journal.append(first)
    second = make_event(
        journal,
        tenant_id=tenant_id,
        aggregate_id=aggregate_id,
        sequence=2,
        previous_digest=persisted_first.integrity.digest,
    )
    persisted_second = journal.append(second)

    history = journal.history(tenant_id, "run", aggregate_id)
    assert [event.sequence for event in history] == [1, 2]
    assert persisted_second.integrity.previous_digest == persisted_first.integrity.digest
    assert persisted_second.integrity.digest == journal.calculate_digest(
        persisted_second, persisted_first.integrity.digest
    )


def test_append_rejects_sequence_gap_and_does_not_persist(journal):
    tenant_id = uuid4()
    aggregate_id = uuid4()
    event = make_event(journal, tenant_id=tenant_id, aggregate_id=aggregate_id, sequence=2)

    with pytest.raises(EventSequenceConflict):
        journal.append(event)

    assert journal.history(tenant_id, "run", aggregate_id) == []


def test_append_rejects_invalid_digest_without_persisting(journal):
    tenant_id = uuid4()
    aggregate_id = uuid4()
    event = make_event(journal, tenant_id=tenant_id, aggregate_id=aggregate_id, sequence=1)
    invalid = event.model_copy(
        update={"integrity": EventIntegrity(previous_digest=None, digest="invalid")}
    )

    with pytest.raises(EventIntegrityError):
        journal.append(invalid)

    assert journal.history(tenant_id, "run", aggregate_id) == []


def test_event_id_is_idempotent_and_collision_fails_closed(journal):
    tenant_id = uuid4()
    aggregate_id = uuid4()
    event = make_event(journal, tenant_id=tenant_id, aggregate_id=aggregate_id, sequence=1)

    assert journal.append(event) == event
    assert journal.append(event) == event

    collision = event.model_copy(update={"payload": {"intent": "different"}})
    with pytest.raises(EventIntegrityError, match="event id collision"):
        journal.append(collision)


def test_tenant_history_isolation(journal):
    aggregate_id = uuid4()
    tenant_a = uuid4()
    tenant_b = uuid4()
    event_a = make_event(journal, tenant_id=tenant_a, aggregate_id=aggregate_id, sequence=1)
    event_b = make_event(journal, tenant_id=tenant_b, aggregate_id=aggregate_id, sequence=1)

    journal.append(event_a)
    journal.append(event_b)

    assert [event.tenant_id for event in journal.tenant_history(tenant_a)] == [tenant_a]
    assert [event.tenant_id for event in journal.tenant_history(tenant_b)] == [tenant_b]
