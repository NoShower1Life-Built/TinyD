from datetime import datetime, timezone
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.events import EventEnvelope, event_hash
from src.store import PostgresEventStore


def make_event(sequence=0, previous_hash=None, event_id=None, payload=None):
    event = EventEnvelope(
        event_id=event_id or f"evt-{sequence}", event_type="NODE_READY", schema_version="1.0",
        aggregate_id="aggregate-1", run_id="run-1", tenant_id="tenant-1", sequence=sequence,
        logical_time=sequence, causation_id=None, correlation_id="corr-1", producer="test",
        payload=payload if payload is not None else {"node": "n1", "sequence": sequence},
        previous_hash=previous_hash, event_hash="0" * 64, metadata={},
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    )
    return EventEnvelope(**{**event.as_dict(), "event_hash": event_hash(event)})


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self): return self
    def __exit__(self, *_): return False

    def execute(self, sql, params):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT pg_advisory_xact_lock"):
            return
        if normalized.startswith("SELECT event_id"):
            found = next((e for e in self.connection.inserted if e.event_id == params[0]), None)
            self.rows = [(found.event_id, found.event_hash, found.sequence, found.tenant_id, found.aggregate_id, found.run_id)] if found else []
        elif normalized.startswith("SELECT event_hash"):
            stream = [e for e in self.connection.inserted if (e.tenant_id, e.aggregate_id, e.run_id) == params]
            found = max(stream, key=lambda e: e.sequence, default=None)
            self.rows = [(found.event_hash, found.sequence)] if found else []
        elif normalized.startswith("INSERT INTO"):
            values = params
            self.connection.inserted.append(EventEnvelope(
                event_id=values[0], event_type=values[1], schema_version=values[2], aggregate_id=values[3],
                run_id=values[4], tenant_id=values[5], sequence=values[6], logical_time=values[7],
                causation_id=values[8], correlation_id=values[9], producer=values[10], payload=values[11],
                previous_hash=values[12], event_hash=values[13], metadata=values[14],
                timestamp=values[15].isoformat() if hasattr(values[15], "isoformat") else values[15]))
        elif normalized.startswith("SELECT event_id, event_type"):
            stream = sorted((e for e in self.connection.inserted if (e.tenant_id, e.aggregate_id, e.run_id) == params), key=lambda e: e.sequence)
            self.rows = [tuple([e.event_id,e.event_type,e.schema_version,e.aggregate_id,e.run_id,e.tenant_id,e.sequence,e.logical_time,e.causation_id,e.correlation_id,e.producer,e.payload,e.previous_hash,e.event_hash,e.metadata,e.timestamp]) for e in stream]

    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return list(self.rows)


class FakeConnection:
    def __init__(self): self.inserted = []; self.commits = 0; self.rollbacks = 0
    def cursor(self): return FakeCursor(self)
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def test_append_is_idempotent_and_does_not_duplicate():
    event = make_event()
    connection = FakeConnection()
    store = PostgresEventStore(connection)
    assert store.append(event).inserted is True
    assert store.append(event).inserted is False
    assert len(connection.inserted) == 1


def test_conflicting_event_id_is_rejected():
    event = make_event()
    store = PostgresEventStore(FakeConnection())
    store.append(event)
    conflict = make_event(event_id=event.event_id, payload={"different": True})
    with pytest.raises(ValueError, match="different event content"):
        store.append(conflict)


def test_sequence_and_predecessor_are_enforced():
    connection = FakeConnection()
    store = PostgresEventStore(connection)
    first = make_event()
    store.append(first)
    with pytest.raises(ValueError, match="not contiguous"):
        store.append(make_event(sequence=2, previous_hash=first.event_hash))
    with pytest.raises(ValueError, match="does not match"):
        store.append(make_event(sequence=1, previous_hash="0" * 64))


def test_read_returns_verified_authoritative_chain():
    connection = FakeConnection()
    store = PostgresEventStore(connection)
    first = make_event()
    second = make_event(1, first.event_hash)
    store.append(first)
    store.append(second)
    events = store.read("tenant-1", "aggregate-1", "run-1")
    assert tuple(e.event_id for e in events) == ("evt-0", "evt-1")
    assert events[1].previous_hash == events[0].event_hash


def test_hash_mismatch_is_rejected_before_database_write():
    event = make_event()
    invalid = EventEnvelope(**{**event.as_dict(), "event_hash": "f" * 64})
    connection = FakeConnection()
    with pytest.raises(ValueError, match="hash does not match"):
        PostgresEventStore(connection).append(invalid)
    assert connection.inserted == []
