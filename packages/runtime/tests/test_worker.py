from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.worker import RuntimeWorker


@dataclass(frozen=True)
class Result:
    inserted: bool


@dataclass
class FakeWork:
    work_id: UUID
    event_id: str
    tenant_id: str
    aggregate_id: str
    run_id: str
    lease_token: UUID
    attempt_count: int = 1


class FakeScheduler:
    def __init__(self, work=None, *, complete_result=True, fail_error=None, renew_result=True):
        self.work = work
        self.complete_result = complete_result
        self.fail_error = fail_error
        self.renew_result = renew_result
        self.completed = []
        self.failed = []
        self.renewed = []

    def claim(self, worker_id, *, lease_duration):
        work, self.work = self.work, None
        return work

    def complete(self, work_id, worker_id, lease_token):
        self.completed.append((work_id, worker_id, lease_token))
        return self.complete_result

    def fail(self, work_id, worker_id, lease_token, error, *, retry_at, max_attempts):
        if self.fail_error:
            raise self.fail_error
        self.failed.append((work_id, worker_id, lease_token, error, retry_at, max_attempts))
        return True

    def renew(self, work_id, worker_id, lease_token, *, lease_duration):
        self.renewed.append((work_id, worker_id, lease_token))
        return self.renew_result


class FakeJournal:
    def __init__(self, event=None, result=None, error=None):
        self.event = event
        self.result = result or Result(inserted=True)
        self.error = error
        self.loaded = []
        self.events = []

    def load_event(self, event_id):
        self.loaded.append(event_id)
        return self.event

    def append(self, event):
        if self.error:
            raise self.error
        self.events.append(event)
        return self.result


def make_work():
    return FakeWork(uuid4(), "event-1", "tenant-1", "aggregate-1", "run-1", uuid4())


def make_event(work, **overrides):
    values = {
        "event_id": work.event_id,
        "tenant_id": work.tenant_id,
        "aggregate_id": work.aggregate_id,
        "run_id": work.run_id,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_worker(scheduler, journal, *, heartbeat_interval=timedelta(seconds=10)):
    return RuntimeWorker(
        scheduler=scheduler,
        journal=journal,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=30),
        max_attempts=3,
        retry_delay=timedelta(seconds=0),
        heartbeat_interval=heartbeat_interval,
    )


def test_process_once_loads_authoritative_event_appends_and_completes():
    work = make_work()
    event = make_event(work)
    scheduler = FakeScheduler(work)
    journal = FakeJournal(event=event, result=Result(inserted=True))
    result = make_worker(scheduler, journal).process_once()
    assert result is not None
    assert result.completed is True
    assert result.appended is True
    assert journal.loaded == [work.event_id]
    assert journal.events == [event]
    assert scheduler.completed == [(work.work_id, "worker-a", work.lease_token)]
    assert scheduler.failed == []


def test_duplicate_journal_append_is_successful_completion():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(event=make_event(work), result=Result(inserted=False))
    result = make_worker(scheduler, journal).process_once()
    assert result is not None
    assert result.completed is True
    assert result.appended is False
    assert scheduler.completed[0][2] == work.lease_token


def test_missing_authoritative_event_is_recorded_and_propagated():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(event=None)
    with pytest.raises(RuntimeError, match="authoritative event"):
        make_worker(scheduler, journal).process_once()
    assert scheduler.failed[0][2] == work.lease_token


def test_authoritative_event_identity_mismatch_is_rejected():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(event=make_event(work, tenant_id="other-tenant"))
    with pytest.raises(RuntimeError, match="tenant_id"):
        make_worker(scheduler, journal).process_once()
    assert journal.events == []
    assert len(scheduler.failed) == 1


def test_append_failure_preserves_primary_error_when_failure_recording_fails():
    work = make_work()
    scheduler = FakeScheduler(work, fail_error=RuntimeError("failure database unavailable"))
    journal = FakeJournal(event=make_event(work), error=RuntimeError("primary database unavailable"))
    with pytest.raises(RuntimeError, match="primary database unavailable"):
        make_worker(scheduler, journal).process_once()
    assert scheduler.completed == []
    assert scheduler.failed == []


def test_lease_loss_after_append_is_failure_not_success():
    work = make_work()
    scheduler = FakeScheduler(work, complete_result=False)
    journal = FakeJournal(event=make_event(work))
    with pytest.raises(RuntimeError, match="lease was lost"):
        make_worker(scheduler, journal).process_once()
    assert len(journal.events) == 1
    assert scheduler.failed[0][2] == work.lease_token


def test_heartbeat_renews_current_fence():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(event=make_event(work))
    worker = make_worker(scheduler, journal)
    stop = __import__("threading").Event()
    lost = __import__("threading").Event()
    thread = __import__("threading").Thread(
        target=worker._heartbeat,
        args=(work.work_id, work.lease_token, stop, lost),
        daemon=True,
    )
    worker.heartbeat_interval = timedelta(milliseconds=1)
    thread.start()
    __import__("time").sleep(0.01)
    stop.set()
    thread.join(timeout=1)
    assert scheduler.renewed
    assert scheduler.renewed[0][2] == work.lease_token
    assert not lost.is_set()


def test_heartbeat_lease_loss_is_signaled():
    work = make_work()
    scheduler = FakeScheduler(work, renew_result=False)
    journal = FakeJournal(event=make_event(work))
    worker = make_worker(scheduler, journal)
    stop = __import__("threading").Event()
    lost = __import__("threading").Event()
    worker.heartbeat_interval = timedelta(milliseconds=1)
    worker._heartbeat(work.work_id, work.lease_token, stop, lost)
    assert lost.is_set()
