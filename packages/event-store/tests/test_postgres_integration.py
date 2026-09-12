from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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


def load_runtime_module(name, filename):
    path = _RUNTIME_SRC / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

_JOURNAL_MODULE = load_runtime_module("tinyd_runtime_event_journal", "event_journal.py")
EventJournal = _JOURNAL_MODULE.EventJournal
_SCHEDULER_MODULE = load_runtime_module("tinyd_runtime_scheduler", "scheduler.py")
DurableScheduler = _SCHEDULER_MODULE.DurableScheduler
sys.modules["event_journal"] = _JOURNAL_MODULE
sys.modules["scheduler"] = _SCHEDULER_MODULE
_WORKER_MODULE = load_runtime_module("tinyd_runtime_worker", "worker.py")
RuntimeWorker = _WORKER_MODULE.RuntimeWorker

DATABASE_URL = os.environ.get("TINYD_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TINYD_TEST_DATABASE_URL is not set")
WORK_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "001_tinyd_work_items.sql"
FENCING_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "002_tinyd_work_item_lease_fencing.sql"


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
            cursor.execute("DROP TABLE IF EXISTS tinyd_work_items")
            cursor.execute("DROP TABLE IF EXISTS tinyd_events")
            cursor.execute(DDL)
            cursor.execute(WORK_MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute(FENCING_MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.commit()
    yield
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS tinyd_work_items")
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


def test_authoritative_event_lookup_returns_verified_event():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        second = make_event(sequence=1, previous_hash=first.event_hash)
        store.append(first)
        store.append(second)
        assert store.get_event(second.event_id) == second
    finally:
        connection.close()


def test_authoritative_event_lookup_detects_payload_tampering():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        first = make_event()
        store.append(first)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE tinyd_events SET payload = '{\"tampered\": true}'::jsonb WHERE event_id = %s", (first.event_id,))
        connection.commit()
        with pytest.raises(ValueError, match="authoritative event hash verification failed"):
            store.get_event(first.event_id)
    finally:
        connection.close()


def test_authoritative_event_lookup_rejects_missing_event():
    connection = connect()
    try:
        store = PostgresEventStore(connection)
        with pytest.raises(KeyError, match="event not found"):
            store.get_event("missing-event")
    finally:
        connection.close()


def test_event_first_scheduler_submission_requires_authoritative_event():
    connection = connect()
    try:
        scheduler = DurableScheduler(connection)
        missing = make_event(event_id="not-persisted")
        with pytest.raises(ValueError, match="durably persisted"):
            scheduler.submit(missing)
        persisted = make_event(event_id="persisted")
        assert PostgresEventStore(connection).append(persisted).inserted is True
        work = scheduler.submit(persisted)
        assert work.event_id == persisted.event_id
        assert work.status == "PENDING"
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
        with pytest.raises(ValueError, match="event_id already exists with different event content"):
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
        with pytest.raises(ValueError, match="event hash does not match canonical event"):
            store.append(tampered)
        assert store.read("tenant-1", "aggregate-1", "run-1") == ()
    finally:
        connection.close()


def test_concurrent_sequence_writers_are_serialized():
    import threading
    setup = connect()
    try:
        first = make_event()
        PostgresEventStore(setup).append(first)
    finally:
        setup.close()

    def append_sequence_one():
        conn = connect()
        try:
            event = make_event(sequence=1, previous_hash=first.event_hash, event_id=threading.current_thread().name)
            try:
                return PostgresEventStore(conn).append(event)
            except Exception as exc:
                return exc
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: append_sequence_one(), range(8)))
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
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
        assert journal.append(first).inserted is True
        assert journal.load("tenant-1", "aggregate-1", "run-1") == (first,)
        assert journal.load_event(first.event_id) == first
    finally:
        connection.close()


def worker_for(scheduler, journal, worker_id="worker-a", resolver=None, max_attempts=3):
    return RuntimeWorker(
        scheduler=scheduler,
        journal=journal,
        worker_id=worker_id,
        lease_duration=timedelta(seconds=30),
        event_resolver=resolver or (lambda work: first),
        max_attempts=max_attempts,
        retry_delay=timedelta(seconds=0),
    )


def test_durable_scheduler_worker_persists_through_event_journal_to_postgres():
    connection = connect()
    try:
        journal = EventJournal(PostgresEventStore(connection))
        scheduler = DurableScheduler(connection)
        first = make_event()
        assert journal.append(first).inserted is True
        scheduler.submit(first)
        result = worker_for(scheduler, journal, resolver=lambda work: first).process_once()
        assert result is not None
        assert result.completed is True
        assert result.appended is False
        assert journal.load("tenant-1", "aggregate-1", "run-1") == (first,)
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count FROM tinyd_work_items WHERE work_id = %s", (str(result.work_id),))
            assert cursor.fetchone() == ("COMPLETED", 1)
            cursor.execute("SELECT count(*) FROM tinyd_events")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def test_durable_worker_idempotent_append_completes_existing_event():
    connection = connect()
    try:
        journal = EventJournal(PostgresEventStore(connection))
        scheduler = DurableScheduler(connection)
        first = make_event()
        assert journal.append(first).inserted is True
        submitted = scheduler.submit(first)
        result = worker_for(scheduler, journal, resolver=lambda work: first).process_once()
        assert result is not None
        assert result.completed is True
        assert result.appended is False
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("COMPLETED", 1)
            cursor.execute("SELECT count(*) FROM tinyd_events")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def test_durable_worker_failure_is_persisted_and_retries():
    connection = connect()
    try:
        journal = EventJournal(PostgresEventStore(connection))
        scheduler = DurableScheduler(connection)
        first = make_event()
        assert journal.append(first).inserted is True
        submitted = scheduler.submit(first)
        failing = worker_for(
            scheduler, journal,
            resolver=lambda work: (_ for _ in ()).throw(RuntimeError("resolver unavailable")),
            max_attempts=2,
        )
        with pytest.raises(RuntimeError, match="resolver unavailable"):
            failing.process_once()
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count, last_error FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("PENDING", 1, "resolver unavailable")
            cursor.execute("UPDATE tinyd_work_items SET available_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)))
        connection.commit()
        result = worker_for(scheduler, journal, worker_id="worker-b", resolver=lambda work: first, max_attempts=2).process_once()
        assert result is not None
        assert result.completed is True
        assert result.appended is False
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count, last_error FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("COMPLETED", 2, None)
            cursor.execute("SELECT count(*) FROM tinyd_events")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def test_durable_worker_lease_loss_is_detected_after_append():
    connection = connect()
    try:
        journal = EventJournal(PostgresEventStore(connection))
        scheduler = DurableScheduler(connection)
        first = make_event()
        assert journal.append(first).inserted is True
        submitted = scheduler.submit(first)

        class LeaseStealingJournal:
            def append(self, event):
                result = journal.append(event)
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE tinyd_work_items SET lease_expires_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)))
                connection.commit()
                assert scheduler.claim("worker-b", lease_duration=timedelta(seconds=30)) is not None
                return result

        worker = worker_for(scheduler, LeaseStealingJournal(), resolver=lambda work: first, max_attempts=2)
        with pytest.raises(RuntimeError, match="lease was lost"):
            worker.process_once()
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, lease_owner, attempt_count FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("LEASED", "worker-b", 2)
            cursor.execute("SELECT count(*) FROM tinyd_events")
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()
