from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.events import EventEnvelope, event_hash
from src.store import DDL, PostgresEventStore

_RUNTIME_SRC = Path(__file__).parents[2] / "runtime" / "src"
_RUNTIME_JOURNAL_PATH = _RUNTIME_SRC / "event_journal.py"
_RUNTIME_JOURNAL_NAME = "tinyd_runtime_event_journal"
_RUNTIME_JOURNAL_SPEC = importlib.util.spec_from_file_location(_RUNTIME_JOURNAL_NAME, _RUNTIME_JOURNAL_PATH)
_RUNTIME_JOURNAL_MODULE = importlib.util.module_from_spec(_RUNTIME_JOURNAL_SPEC)
assert _RUNTIME_JOURNAL_SPEC.loader is not None
sys.modules[_RUNTIME_JOURNAL_NAME] = _RUNTIME_JOURNAL_MODULE
_RUNTIME_JOURNAL_SPEC.loader.exec_module(_RUNTIME_JOURNAL_MODULE)
EventJournal = _RUNTIME_JOURNAL_MODULE.EventJournal

# worker.py supports normal package-relative imports in production. This integration
# test loads it from a file because packages/runtime is not installed as a package
# under the event-store test's PYTHONPATH. Register the already-loaded journal module
# under the fallback name so the worker's standalone-load path resolves the same
# module object rather than requiring a second copy.
sys.modules["event_journal"] = _RUNTIME_JOURNAL_MODULE
_RUNTIME_WORKER_PATH = _RUNTIME_SRC / "worker.py"
_RUNTIME_WORKER_NAME = "tinyd_runtime_worker"
_RUNTIME_WORKER_SPEC = importlib.util.spec_from_file_location(_RUNTIME_WORKER_NAME, _RUNTIME_WORKER_PATH)
_RUNTIME_WORKER_MODULE = importlib.util.module_from_spec(_RUNTIME_WORKER_SPEC)
assert _RUNTIME_WORKER_SPEC.loader is not None
sys.modules[_RUNTIME_WORKER_NAME] = _RUNTIME_WORKER_MODULE
_RUNTIME_WORKER_SPEC.loader.exec_module(_RUNTIME_WORKER_MODULE)
RuntimeScheduler = _RUNTIME_WORKER_MODULE.RuntimeScheduler
RuntimeWorker = _RUNTIME_WORKER_MODULE.RuntimeWorker

DATABASE_URL = os.environ.get("TINYD_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TINYD_TEST_DATABASE_URL is not set")


def make_event(sequence=0, previous_hash=None, event_id=None, payload=None, aggregate_id="aggregate-1"):
    event = EventEnvelope(
        event_id=event_id or f"evt-{sequence}", event_type="NODE_READY", schema_version="1.0",
        aggregate_id=aggregate_id, run_id="run-1", tenant_id="tenant-1", sequence=sequence,
        logical_time=sequence, causation_id=None, correlation_id="corr-1",
        producer="postgres-integration-test",
        payload=payload if payload is not None else {"node": "n1", "sequence": sequence},
        previous_hash=previous_hash, event_hash="0" * 64, metadata={},
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    )
    return EventEnvelope(**{**event.as_dict(), "event_hash": event_hash(event)})


def connect():
    connection = psycopg.connect(DATABASE_URL)
    connection.autocommit = False
    return connection


@pytest.fixture(autouse=True)
def clean_database():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS tinyd_events")
            cursor.execute(DDL)
        connection.commit()
    yield
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS tinyd_events")
        connection.commit()


def test_schema_creation_and_append_read_round_trip():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        assert store.append(first).inserted is True
        assert store.read("tenant-1", "aggregate-1", "run-1") == (first,)
    finally:
        connection.close()


def test_duplicate_append_is_idempotent():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        assert store.append(first).inserted is True
        duplicate = store.append(first)
        assert duplicate.inserted is False
        assert store.read("tenant-1", "aggregate-1", "run-1") == (first,)
    finally:
        connection.close()


def test_conflicting_event_id_is_rejected():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event(event_id="same-id")
        store.append(first)
        conflicting = make_event(event_id="same-id", payload={"different": True})
        with pytest.raises(ValueError, match="event_id conflict"):
            store.append(conflicting)
        assert store.read("tenant-1", "aggregate-1", "run-1") == (first,)
    finally:
        connection.close()


def test_sequence_and_predecessor_are_enforced():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        store.append(first)
        invalid = make_event(sequence=2, previous_hash=first.event_hash)
        with pytest.raises(ValueError, match="not contiguous"):
            store.append(invalid)
        invalid_prev = make_event(sequence=1, previous_hash="f" * 64)
        with pytest.raises(ValueError, match="previous_hash"):
            store.append(invalid_prev)
    finally:
        connection.close()


def test_read_returns_verified_authoritative_chain():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        second = make_event(sequence=1, previous_hash=first.event_hash)
        store.append(first)
        store.append(second)
        assert store.read("tenant-1", "aggregate-1", "run-1") == (first, second)
    finally:
        connection.close()


def test_hash_mismatch_is_rejected_before_db_write():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        tampered = EventEnvelope(**{**first.as_dict(), "payload": {"tampered": True}})
        with pytest.raises(ValueError, match="hash mismatch"):
            store.append(tampered)
        assert store.read("tenant-1", "aggregate-1", "run-1") == ()
    finally:
        connection.close()


def test_concurrent_sequence_writers_are_serialized():
    import threading

    connection = connect()
    connection.close()

    def append_sequence_one():
        conn = connect()
        try:
            store = PostgresEventStore(conn)
            event = make_event(sequence=1, previous_hash=first.event_hash, event_id=threading.current_thread().name)
            try:
                return store.append(event)
            except Exception as exc:
                return exc
        finally:
            conn.close()

    setup = connect()
    try:
        store = PostgresEventStore(setup)
        first = make_event()
        store.append(first)
    finally:
        setup.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: append_sequence_one(), range(8)))

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 7
    assert all("not contiguous" in str(error) for error in failures)


def test_rollback_leaves_stream_unchanged_after_invalid_append():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        store.append(first)
        invalid = make_event(sequence=2, previous_hash=first.event_hash)
        with pytest.raises(ValueError):
            store.append(invalid)
        assert store.read("tenant-1", "aggregate-1", "run-1") == (first,)
    finally:
        connection.close()


def test_chain_tamper_is_detected_on_read():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        store.append(first)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE tinyd_events SET payload = '{\"tampered\": true}'::jsonb WHERE event_id = %s", (first.event_id,))
        connection.commit()
        with pytest.raises(ValueError, match="hash mismatch"):
            store.read("tenant-1", "aggregate-1", "run-1")
    finally:
        connection.close()


def test_runtime_event_journal_uses_postgres_as_authoritative_boundary():
    connection = connect()
    try:
        journal = EventJournal(PostgresEventStore(connection))
        first = make_event()
        result = journal.append(first)
        assert result.inserted is True
        assert journal.load("tenant-1", "aggregate-1", "run-1") == (first,)
    finally:
        connection.close()


def test_scheduler_worker_persists_through_event_journal_to_postgres():
    connection = connect()
    try:
        journal = EventJournal(PostgresEventStore(connection))
        scheduler = RuntimeScheduler()
        worker = RuntimeWorker(scheduler=scheduler, journal=journal)
        first = make_event()

        scheduler.submit(first)
        result = worker.process_once(timeout=1.0)

        assert result.inserted is True
        assert journal.load("tenant-1", "aggregate-1", "run-1") == (first,)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM tinyd_events")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()
