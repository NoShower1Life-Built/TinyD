from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import UUID

import psycopg

from src.scheduler import DurableScheduler


DATABASE_URL = os.environ.get("TINYD_TEST_DATABASE_URL")
MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "001_tinyd_work_items.sql"


if not DATABASE_URL:
    raise RuntimeError("TINYD_TEST_DATABASE_URL is required")


def connection():
    return psycopg.connect(DATABASE_URL)


def reset_schema() -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS tinyd_work_items")
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
        conn.commit()


def event(event_id: str = "event-1", tenant_id: str = "tenant-1"):
    return SimpleNamespace(
        event_id=event_id,
        tenant_id=tenant_id,
        aggregate_id="aggregate-1",
        run_id="run-1",
    )


def test_migration_is_idempotent() -> None:
    reset_schema()
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
        conn.commit()
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM tinyd_work_items")
            assert cursor.fetchone()[0] == 0


def test_submit_is_idempotent_per_tenant_event() -> None:
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        first = scheduler.submit(event())
        second = scheduler.submit(event())
        assert first.work_id == second.work_id
        assert first.status == "PENDING"
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM tinyd_work_items")
            assert cursor.fetchone()[0] == 1


def test_claim_sets_lease_and_increments_attempt() -> None:
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        assert claimed.work_id == submitted.work_id
        assert claimed.status == "LEASED"
        assert claimed.lease_owner == "worker-a"
        assert claimed.lease_expires_at is not None
        assert claimed.attempt_count == 1


def test_concurrent_claim_allows_only_one_active_lease() -> None:
    reset_schema()
    with connection() as conn:
        DurableScheduler(conn).submit(event())

    def claim(worker_id: str):
        with connection() as conn:
            return DurableScheduler(conn).claim(worker_id, lease_duration=timedelta(seconds=30))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("worker-a", "worker-b")))

    assert sum(result is not None for result in results) == 1
    owners = [result.lease_owner for result in results if result is not None]
    assert owners in [["worker-a"], ["worker-b"]]


def test_wrong_worker_cannot_complete_lease() -> None:
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        assert scheduler.complete(submitted.work_id, "worker-b") is False
        assert scheduler.complete(submitted.work_id, "worker-a") is True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status, completed_at, lease_owner, lease_expires_at "
                "FROM tinyd_work_items WHERE work_id = %s",
                (str(submitted.work_id),),
            )
            status, completed_at, owner, expires = cursor.fetchone()
            assert status == "COMPLETED"
            assert completed_at is not None
            assert owner is None
            assert expires is None


def test_expired_lease_is_reclaimable() -> None:
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE tinyd_work_items SET lease_expires_at = %s WHERE work_id = %s",
                (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)),
            )
        conn.commit()
        reclaimed = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert reclaimed is not None
        assert reclaimed.work_id == submitted.work_id
        assert reclaimed.lease_owner == "worker-b"
        assert reclaimed.attempt_count == 2


def test_retry_and_terminal_failure_are_durable() -> None:
    reset_schema()
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event())
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        assert scheduler.fail(
            submitted.work_id,
            "worker-a",
            "temporary failure",
            retry_at=retry_at,
            max_attempts=2,
        ) is True
        retry = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert retry is None
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status, attempt_count, last_error FROM tinyd_work_items WHERE work_id = %s",
                (str(submitted.work_id),),
            )
            assert cursor.fetchone() == ("PENDING", 1, "temporary failure")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tinyd_work_items SET available_at = %s WHERE work_id = %s",
            (datetime.now(timezone.utc) - timedelta(seconds=1), str(submitted.work_id)),
        )
        conn.commit()
        cursor.close()
        retry = scheduler.claim("worker-b", lease_duration=timedelta(seconds=30))
        assert retry is not None
        assert retry.attempt_count == 2
        assert scheduler.fail(
            submitted.work_id,
            "worker-b",
            "permanent failure",
            retry_at=None,
            max_attempts=2,
        ) is True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status, attempt_count, last_error FROM tinyd_work_items WHERE work_id = %s",
                (str(submitted.work_id),),
            )
            assert cursor.fetchone() == ("FAILED", 2, "permanent failure")
