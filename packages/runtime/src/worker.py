from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any, Callable
from uuid import UUID

try:
    from .event_journal import EventJournal
    from .scheduler import DurableScheduler, WorkItem
except ImportError:
    from event_journal import EventJournal
    from scheduler import DurableScheduler, WorkItem


EventResolver = Callable[[WorkItem], Any]


@dataclass(frozen=True, slots=True)
class WorkerResult:
    work_id: UUID
    event_id: str
    completed: bool
    appended: bool


class RuntimeWorker:
    """Durable worker: claim, resolve, append through EventJournal, then acknowledge."""

    def __init__(
        self,
        scheduler: DurableScheduler,
        journal: EventJournal,
        *,
        worker_id: str,
        lease_duration: timedelta,
        event_resolver: EventResolver,
        max_attempts: int = 3,
        retry_delay: timedelta = timedelta(seconds=1),
    ) -> None:
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if not callable(event_resolver):
            raise ValueError("event_resolver must be callable")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if retry_delay < timedelta(0):
            raise ValueError("retry_delay must not be negative")
        self.scheduler = scheduler
        self.journal = journal
        self.worker_id = worker_id
        self.lease_duration = lease_duration
        self.event_resolver = event_resolver
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self._stop = Event()

    def process_once(self) -> WorkerResult | None:
        work = self.scheduler.claim(self.worker_id, lease_duration=self.lease_duration)
        if work is None:
            return None
        try:
            event = self.event_resolver(work)
            if event is None:
                raise RuntimeError(f"event resolver returned no event for {work.event_id}")
            if getattr(event, "event_id", None) != work.event_id:
                raise RuntimeError("resolved event_id does not match work item")
            if getattr(event, "tenant_id", None) != work.tenant_id:
                raise RuntimeError("resolved tenant_id does not match work item")
            if getattr(event, "aggregate_id", None) != work.aggregate_id:
                raise RuntimeError("resolved aggregate_id does not match work item")
            if getattr(event, "run_id", None) != work.run_id:
                raise RuntimeError("resolved run_id does not match work item")

            result = self.journal.append(event)
            inserted = getattr(result, "inserted", None)
            if inserted not in (True, False):
                raise RuntimeError("event journal append returned an invalid result")
            if not self.scheduler.complete(work.work_id, self.worker_id):
                raise RuntimeError("worker lease was lost before completion")
            return WorkerResult(
                work_id=work.work_id,
                event_id=work.event_id,
                completed=True,
                appended=inserted,
            )
        except Exception as exc:
            self.scheduler.fail(
                work.work_id,
                self.worker_id,
                str(exc),
                retry_at=datetime.now(timezone.utc) + self.retry_delay,
                max_attempts=self.max_attempts,
            )
            raise

    def run(self, poll_interval: float = 0.5) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        while not self._stop.is_set():
            try:
                result = self.process_once()
            except Exception:
                if self._stop.is_set():
                    break
                self._stop.wait(poll_interval)
                continue
            if result is None:
                self._stop.wait(poll_interval)

    def start(self, poll_interval: float = 0.5) -> Thread:
        thread = Thread(target=self.run, kwargs={"poll_interval": poll_interval}, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()


def build_worker(
    scheduler: DurableScheduler,
    journal: EventJournal,
    *,
    worker_id: str,
    lease_duration: timedelta,
    event_resolver: EventResolver,
    max_attempts: int = 3,
    retry_delay: timedelta = timedelta(seconds=1),
) -> RuntimeWorker:
    return RuntimeWorker(
        scheduler=scheduler,
        journal=journal,
        worker_id=worker_id,
        lease_duration=lease_duration,
        event_resolver=event_resolver,
        max_attempts=max_attempts,
        retry_delay=retry_delay,
    )
