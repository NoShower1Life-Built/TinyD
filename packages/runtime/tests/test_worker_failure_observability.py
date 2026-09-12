from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.worker import RuntimeWorker


@dataclass
class Work:
    work_id: UUID
    event_id: str
    tenant_id: str
    aggregate_id: str
    run_id: str
    lease_token: UUID


class Scheduler:
    def __init__(self, work: Work, *, fail_result: bool = True, fail_error: Exception | None = None):
        self.work = work
        self.fail_result = fail_result
        self.fail_error = fail_error
        self.failed = []

    def claim(self, worker_id, *, lease_duration):
        return self.work

    def complete(self, work_id, worker_id, lease_token):
        return True

    def fail(self, work_id, worker_id, lease_token, error, *, retry_at, max_attempts):
        if self.fail_error is not None:
            raise self.fail_error
        self.failed.append((work_id, worker_id, lease_token, error, retry_at, max_attempts))
        return self.fail_result


class Journal:
    def __init__(self, event=None, error=None):
        self.event = event
        self.error = error

    def load_event(self, event_id):
        return self.event

    def append(self, event):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(inserted=True)


def make_work() -> Work:
    return Work(uuid4(), "event-1", "tenant-1", "aggregate-1", "run-1", uuid4())


def make_worker(scheduler, journal):
    return RuntimeWorker(
        scheduler=scheduler,
        journal=journal,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=30),
        heartbeat_connection_factory=lambda: SimpleNamespace(close=lambda: None),
        max_attempts=3,
        retry_delay=timedelta(seconds=0),
        heartbeat_interval=timedelta(seconds=10),
    )


def test_failure_recording_success_is_explicit(monkeypatch):
    work = make_work()
    scheduler = Scheduler(work, fail_result=True)
    journal = Journal(error=RuntimeError("primary failure"))
    monkeypatch.setattr(RuntimeWorker, "_heartbeat", lambda self, *args: None)

    worker = make_worker(scheduler, journal)
    with pytest.raises(RuntimeError, match="primary failure"):
        worker.process_once()

    outcome = worker.last_failure_outcome
    assert outcome is not None
    assert outcome.status == "RECORDED"
    assert outcome.recording_error is None
    assert outcome.recovery == "durable_retry_or_terminal_failure"
    assert scheduler.failed and scheduler.failed[0][2] == work.lease_token


def test_failure_recording_failure_is_observable_without_masking_primary_error(monkeypatch):
    work = make_work()
    scheduler = Scheduler(work, fail_error=RuntimeError("failure store unavailable"))
    journal = Journal(error=RuntimeError("primary failure"))
    monkeypatch.setattr(RuntimeWorker, "_heartbeat", lambda self, *args: None)

    worker = make_worker(scheduler, journal)
    with pytest.raises(RuntimeError, match="primary failure") as raised:
        worker.process_once()

    outcome = worker.last_failure_outcome
    assert outcome is not None
    assert outcome.status == "RECORDING_FAILED"
    assert outcome.recording_error == "failure store unavailable"
    assert outcome.recovery == "lease_expiry_or_reclamation"
    assert "durable failure recording failed" in raised.value.__notes__


def test_fenced_failure_recording_failure_is_observable_and_recoverable(monkeypatch):
    work = make_work()
    scheduler = Scheduler(work, fail_result=False)
    journal = Journal(error=RuntimeError("primary failure"))
    monkeypatch.setattr(RuntimeWorker, "_heartbeat", lambda self, *args: None)

    worker = make_worker(scheduler, journal)
    with pytest.raises(RuntimeError, match="primary failure") as raised:
        worker.process_once()

    outcome = worker.last_failure_outcome
    assert outcome is not None
    assert outcome.status == "LEASE_LOST"
    assert outcome.recording_error is None
    assert outcome.recovery == "lease_expiry_or_reclamation"
    assert "lease expiry/reclamation" in raised.value.__notes__[0]
