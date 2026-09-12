from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.worker import RuntimeWorker


@dataclass(frozen=True)
class Result:
    inserted: bool


@dataclass
class FakeWork:
    work_id: object
    event_id: str
    tenant_id: str
    aggregate_id: str
    run_id: str
    attempt_count: int = 1


class FakeScheduler:
    def __init__(self, work=None):
        self.work = work
        self.completed = []
        self.failed = []

    def claim(self, worker_id, *, lease_duration):
        work, self.work = self.work, None
        return work

    def complete(self, work_id, worker_id):
        self.completed.append((work_id, worker_id))
        return True

    def fail(self, work_id, worker_id, error, *, retry_at, max_attempts):
        self.failed.append((work_id, worker_id, error, retry_at, max_attempts))
        return True


class FakeJournal:
    def __init__(self, result=None, error=None):
        self.result = result or Result(inserted=True)
        self.error = error
        self.events = []

    def append(self, event):
        if self.error:
            raise self.error
        self.events.append(event)
        return self.result


def make_worker(scheduler, journal, resolver):
    return RuntimeWorker(
        scheduler=scheduler,
        journal=journal,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=30),
        event_resolver=resolver,
        max_attempts=3,
        retry_delay=timedelta(seconds=0),
    )


def make_work():
    return FakeWork(uuid4(), "event-1", "tenant-1", "aggregate-1", "run-1")


def make_event(work):
    return SimpleNamespace(
        event_id=work.event_id,
        tenant_id=work.tenant_id,
        aggregate_id=work.aggregate_id,
        run_id=work.run_id,
    )


def test_process_once_claims_resolves_appends_and_completes():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(Result(inserted=True))
    event = make_event(work)
    worker = make_worker(scheduler, journal, lambda item: event)

    result = worker.process_once()

    assert result is not None
    assert result.work_id == work.work_id
    assert result.event_id == work.event_id
    assert result.completed is True
    assert result.appended is True
    assert journal.events == [event]
    assert scheduler.completed == [(work.work_id, "worker-a")]
    assert scheduler.failed == []


def test_duplicate_journal_append_is_successful_completion():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(Result(inserted=False))
    worker = make_worker(scheduler, journal, make_event)

    result = worker.process_once()

    assert result is not None
    assert result.completed is True
    assert result.appended is False
    assert scheduler.completed == [(work.work_id, "worker-a")]


def test_append_failure_is_recorded_as_retry_and_propagated():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal(error=RuntimeError("database unavailable"))
    worker = make_worker(scheduler, journal, make_event)

    with pytest.raises(RuntimeError, match="database unavailable"):
        worker.process_once()

    assert scheduler.completed == []
    assert len(scheduler.failed) == 1
    _, owner, error, retry_at, max_attempts = scheduler.failed[0]
    assert owner == "worker-a"
    assert error == "database unavailable"
    assert retry_at.tzinfo is not None
    assert max_attempts == 3


def test_resolved_event_identity_mismatch_is_rejected_and_failed():
    work = make_work()
    scheduler = FakeScheduler(work)
    journal = FakeJournal()
    bad_event = SimpleNamespace(
        event_id="wrong-event",
        tenant_id=work.tenant_id,
        aggregate_id=work.aggregate_id,
        run_id=work.run_id,
    )
    worker = make_worker(scheduler, journal, lambda item: bad_event)

    with pytest.raises(RuntimeError, match="event_id"):
        worker.process_once()

    assert journal.events == []
    assert len(scheduler.failed) == 1


def test_lease_loss_after_append_is_failure_not_success():
    work = make_work()
    scheduler = FakeScheduler(work)
    scheduler.complete = lambda work_id, worker_id: False
    journal = FakeJournal()
    worker = make_worker(scheduler, journal, make_event)

    with pytest.raises(RuntimeError, match="lease was lost"):
        worker.process_once()

    assert len(journal.events) == 1
    assert len(scheduler.failed) == 1
