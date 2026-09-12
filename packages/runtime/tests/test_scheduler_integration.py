from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

import psycopg
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parents[2] / "event-store"))

from src.events import EventEnvelope, event_hash
from src.store import DDL, PostgresEventStore
from src.scheduler import DurableScheduler


DATABASE_URL = os.environ.get("TINYD_TEST_DATABASE_URL")
MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "001_tinyd_work_items.sql"
FENCING_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "002_tinyd_work_item_lease_fencing.sql"

if not DATABASE_URL:
    raise RuntimeError("TINYD_TEST_DATABASE_URL is required")


def connection():
    return psycopg.connect(DATABASE_URL)


def make_event(event_id: str = "event-1", tenant_id: str = "tenant-1") -> EventEnvelope:
    event = EventEnvelope(
        event_id=event_id,
        event_type="NODE_READY",
        schema_version="1.0",
        aggregate_id="aggregate-1",
        run_id="run-1",
        tenant_id=tenant_id,
        sequence=0,
        logical_time=0,
        causation_id=None,
        correlation_id="corr-1",
        producer="scheduler-integration-test",
        payload={"node": "n1"},
        previous_hash=None,
        event_hash="0" * 64,
        metadata={},
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
    with connection() as conn:
        PostgresEventStore(conn).append(make_event())


def test_migration_is_idempotent():
    reset_schema()
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute(FENCING_MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute("SELECT count(*) FROM tinyd_work_items")
            assert cursor.fetchone()[0] == 0
        conn.commit()


def test_submit_is_idempotent_per_tenant_event():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        first = make_event()
        first = PostgresEventStore(conn).append(first).event
        first_work = scheduler.submit(first)
        second = scheduler.submit(first)
        assert first_work.work_id == second.work_id
        assert first_work.status == "PENDING"


def test_submit_rejects_event_not_in_authoritative_ledger():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        with pytest.raises(ValueError, match="durably persisted"):
            scheduler.submit(make_event(event_id="missing"))


def test_claim_sets_fenced_lease_and_increments_attempt():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        event = make_event()
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
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        event = make_event()
        scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=1))
        assert claimed is not None
        assert claimed.lease_token is not None
        assert scheduler.renew(claimed.work_id, "worker-a", claimed.lease_token, lease_duration=timedelta(seconds=30)) is True
        assert scheduler.renew(claimed.work_id, "worker-b", claimed.lease_token, lease_duration=timedelta(seconds=30)) is False
        assert scheduler.renew(claimed.work_id, "worker-a", UUID(int=0), lease_duration=timedelta(seconds=30)) is False


def test_stale_fenced_worker_cannot_complete():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        event = make_event()
        scheduler.submit(event)
        first = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert first is not None
        with conn.cursor() as cursor:
            cursor.execute("UPDATE tinyd_work_items SET lease_expires_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(first.work_id)))
        conn.commit()
        second = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert second is not None
        assert second.lease_token != first.lease_token
        assert scheduler.complete(first.work_id, "worker-a", first.lease_token) is False
        assert scheduler.complete(second.work_id, "worker-b", second.lease_token) is True


def test_concurrent_claim_allows_only_one_active_lease():
    reset_schema()
    with connection() as conn:
        DurableScheduler(conn).submit(make_event())

    def claim(worker_id: str):
        with connection() as conn:
            return DurableScheduler(conn).claim(worker_id, lease_duration=timedelta(seconds=30))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("worker-a", "worker-b")))

    assert sum(result is not None for result in results) == 1


def test_wrong_worker_cannot_complete_lease():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(make_event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        assert scheduler.complete(submitted.work_id, "worker-b", claimed.lease_token) is False
        assert scheduler.complete(submitted.work_id, "worker-a", claimed.lease_token) is True


def test_expired_lease_is_reclaimable_with_new_fence():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(make_event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        with conn.cursor() as cursor:
            cursor.execute("UPDATE tinyd_work_items SET lease_expires_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)))
        conn.commit()
        reclaimed = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert reclaimed is not None
        assert reclaimed.work_id == submitted.work_id
        assert reclaimed.lease_owner == "worker-b"
        assert reclaimed.lease_token != claimed.lease_token
        assert reclaimed.attempt_count == 2


def test_retry_and_terminal_failure_are_durable_and_fenced():
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(make_event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        assert scheduler.fail(submitted.work_id, "worker-a", claimed.lease_token, "temporary failure", retry_at=retry_at, max_attempts=2) is True
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count, last_error, lease_token FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("PENDING", 1, "temporary failure", None)
        with conn.cursor() as cursor:
            cursor.execute("UPDATE tinyd_work_items SET available_at = %s WHERE work_id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)))
        conn.commit()
        retry = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert retry is not None
        assert retry.attempt_count == 2
        assert scheduler.fail(submitted.work_id, "worker-b", retry.lease_token, "permanent failure", retry_at=None, max_attempts=2) is True
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, attempt_count, last_error, lease_token FROM tinyd_work_items WHERE work_id = %s", (str(submitted.work_id),))
            assert cursor.fetchone() == ("FAILED", 2, "permanent failure", None)


# UUID is imported after the test definitions to keep the production scheduler import surface explicit.
from uuid import UUID
