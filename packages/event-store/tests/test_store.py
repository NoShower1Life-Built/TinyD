from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from packages.event_store.src.events import EventEnvelope, event_hash
from packages.event_store.src.store import PostgresEventStore


def make_event(sequence=0, previous_hash=None, event_id=None):
    event = EventEnvelope(
        event_id=event_id or f"evt-{sequence}",
        event_type="NODE_READY",
        schema_version="1.0",
        aggregate_id="aggregate-1",
        run_id="run-1",
        tenant_id="tenant-1",
        sequence=sequence,
        logical_time=sequence,
        causation_id=None,
        correlation_id="corr-1",
        producer="test",
        payload={"node": "n1", "sequence": sequence},
        previous_hash=previous_hash,
        event_hash="0" * 64,
        metadata={},
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    )
    return EventEnvelope(**{**event.as_dict(), "event_hash": event_hash(event)})


def test_postgres_store_append_is_idempotent_for_same_event():
    event = make_event()
    connection = FakeConnection()
    store = PostgresEventStore(connection)

    first = store.append(event)
    second = store.append(event)

    assert first.inserted is True
    assert second.inserted is False
    assert len(connection.inserted) == 1


def test_postgres_store_rejects_conflicting_duplicate_event_id():
    event = make_event()
    connection = FakeConnection()
    store = PostgresEventStore(connection)
    store.append(event)

    conflicting = make_event(event_id=event.event_id)
    conflicting = EventEnvelope(**{**conflicting.as_dict(), "payload": {"different": True}})
    conflicting = EventEnvelope(**{**conflicting.as_dict(), "event_hash": event_hash(conflicting)})

    with pytest.raises(ValueError, match="different event content"):
        store.append(conflicting)


def test_postgres_store_enforces_chain_head():
    first = make_event()
    connection = FakeConnection()
    store = PostgresEventStore(connection)
    store.append(first)

    bad = make_event(sequence=2, previous_hash=first.event_hash)
    with pytest.raises(ValueError, match="not contiguous"):
        store.append(bad)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.mode = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT event_id"):
            event_id = params[0]
            found = next((e for e in self.connection.inserted if e.event_id == event_id), None)
            self.rows = [(found.event_id, found.event_hash, found.sequence, found.tenant_id, found.aggregate_id, found.run_id)] if found else []
        elif normalized.startswith("SELECT event_hash"):
            stream = [e for e in self.connection.inserted if (e.tenant_id, e.aggregate_id, e.run_id) == params]
            found = max(stream, key=lambda e: e.sequence, default=None)
            self.rows = [(found.event_hash, found.sequence, found.tenant_id, found.aggregate_id, found.run_id)] if found else []
        elif normalized.startswith("INSERT INTO"):
            self.connection.inserted.append(self.connection.pending)
            self.connection.pending = None

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.inserted = []
        self.pending = None

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        return None
