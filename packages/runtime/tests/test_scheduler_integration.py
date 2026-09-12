from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
from uuid import UUID

import psycopg
import pytest

RUNTIME_SRC = Path(__file__).parents[1] / "src"
EVENT_STORE_SRC = Path(__file__).parents[2] / "event-store" / "src"
MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "001_tinyd_work_items.sql"
FENCING_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "002_tinyd_work_item_lease_fencing.sql"
DATABASE_URL = os.environ.get("TINYD_TEST_DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("TINYD_TEST_DATABASE_URL is required")


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_event_store() -> tuple[ModuleType, ModuleType]:
    package_name = "tinyd_event_store_testpkg"
    package = ModuleType(package_name)
    package.__path__ = [str(EVENT_STORE_SRC)]
    sys.modules[package_name] = package
    events = load_module(f"{package_name}.events", EVENT_STORE_SRC / "events.py")
    store = load_module(f"{package_name}.store", EVENT_STORE_SRC / "store.py")
    return events, store


EVENTS, STORE = load_event_store()
SCHEDULER = load_module("tinyd_scheduler", RUNTIME_SRC / "scheduler.py")
EventEnvelope = EVENTS.EventEnvelope
event_hash = EVENTS.event_hash
DDL = STORE.DDL
PostgresEventStore = STORE.PostgresEventStore
DurableScheduler = SCHEDULER.DurableScheduler


def connection():
    return psycopg.connect(DATABASE_URL)


def make_event(event_id: str = "event-1", tenant_id: str = "tenant-1"):
    event = EventEnvelope(
        event_id=event_id, event_type="NODE_READY", schema_version="1.0",
        aggregate_id="aggregate-1", run_id="run-1", tenant_id=tenant_id,
        sequence=0, logical_time=0, causation_id=None, correlation_id="corr-1",
        producer="scheduler-integration-test", payload={"node": "n1"},
        previous_hash=None, event_hash="0" * 64, metadata={},
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    )
    return EventEnvelope(**{**event.as_dict(), "event_hash": event_hash(event)})


def reset_schema() -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS tinyd_work_items")
            cursor.execute("DROP TABLE IF EXISTS tinyd_events")
            cursor.execute(DDL)
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute(FENCING_MIGRATION_PATH.read_text(encoding="utf-8"))
        conn.commit()


def persist_event(event):
    with connection() as conn:
        PostgresEventStore(conn).append(event)


def test_migration_is_idempotent():
    reset_schema()
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute(FENCING_MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute("SELECT count(*) FROM tinyd_work_items")
            assert cursor.fetchone()[0] == 0
        conn.commit()


def test_submit_requires_authoritative_event():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        with pytest.raises(ValueError, match="durably persisted"):
            scheduler.submit(make_event())
    event = make_event()
    persist_event(event)
    with connection() as conn:
        work = DurableScheduler(conn).submit(event)
        assert work.status == "PENDING"


def test_submit_is_idempotent_per_tenant_event():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        first = scheduler.submit(event)
        second = scheduler.submit(event)
        assert first.work_id == second.work_id
        assert first.status == "PENDING"


def test_claim_sets_fenced_lease_and_increments_attempt():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        assert claimed.status == "LEASED"
        assert claimed.lease_owner == "worker-a"
        assert claimed.lease_token is not None
        assert claimed.lease_expires_at is not None
        assert claimed.attempt_count == 1


def test_renew_requires_current_fencing_token():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=1))
        assert claimed is not None and claimed.lease_token is not None
        assert scheduler.renew(claimed.work_id, "worker-a", claimed.lease_token, lease_duration=timedelta(seconds=30)) is True
        assert scheduler.renew(claimed.work_id, "worker-b", claimed.lease_token, lease_duration=timedelta(seconds=30)) is False
        assert scheduler.renew(claimed.work_id, "worker-a", UUID(int=0), lease_duration=timedelta(seconds=30)) is False


def test_stale_fenced_worker_cannot_complete():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event)
        first = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert first is not None and first.lease_token is not None
        with conn.cursor() as cursor:
            cursor.execute("UPDATE tinyd_work_items SET lease_expires_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(first.work_id)))
        conn.commit()
        second = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert second is not None and second.lease_token is not None
        assert second.lease_token != first.lease_token
        assert scheduler.complete(submitted.work_id, "worker-a", first.lease_token) is False
        assert scheduler.complete(second.work_id, "worker-b", second.lease_token) is True


def test_concurrent_claim_allows_only_one_active_lease():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        DurableScheduler(conn).submit(event)

    def claim(worker_id: str):
        with connection() as conn:
            return DurableScheduler(conn).claim(worker_id, lease_duration=timedelta(seconds=30))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("worker-a", "worker-b")))
    assert sum(result is not None for result in results) == 1


def test_wrong_worker_cannot_complete_lease():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None and claimed.lease_token is not None
        assert scheduler.complete(submitted.work_id, "worker-b", claimed.lease_token) is False
        assert scheduler.complete(submitted.work_id, "worker-a", claimed.lease_token) is True


def test_expired_lease_is_reclaimable_with_new_fence():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        with conn.cursor() as cursor:
            cursor.execute("UPDATE tinyd_work_items SET lease_expires_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)))
        conn.commit()
        reclaimed = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert reclaimed is not None
        assert reclaimed.work_id == submitted.work_id
        assert reclaimed.lease_token != claimed.lease_token
        assert reclaimed.attempt_count == 2


def test_retry_and_terminal_failure_are_durable_and_fenced():
    reset_schema()
    event = make_event()
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None and claimed.lease_token is not None
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        assert scheduler.fail(submitted.work_id, "worker-a", claimed.lease_token, "temporary failure", retry_at=retry_at, max_attempts=2) is True
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count, last_error, lease_token FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("PENDING", 1, "temporary failure", None)
        with conn.cursor() as cursor:
            cursor.execute("UPDATE tinyd_work_items SET available_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)))
        conn.commit()
        retry = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert retry is not None and retry.lease_token is not None
        assert retry.attempt_count == 2
        assert scheduler.fail(submitted.work_id, "worker-b", retry.lease_token, "permanent failure", retry_at=None, max_attempts=2) is True
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count, last_error, lease_token FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("FAILED", 2, "permanent failure", None)
