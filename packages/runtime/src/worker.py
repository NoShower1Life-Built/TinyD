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
    """Durable worker using authoritative event resolution and fenced leases."""

    def __init__(
        self,
        scheduler: DurableScheduler,
        journal: EventJournal,
        *,
        worker_id: str,
        lease_duration: timedelta,
        max_attempts: int = 3,
        retry_delay: timedelta = timedelta(seconds=1),
        heartbeat_interval: timedelta | None = None,
    ) -> None:
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if retry_delay < timedelta(0):
            raise ValueError("retry_delay must not be negative")
        interval = heartbeat_interval or lease_duration / 3
        if interval <= timedelta(0) or interval >= lease_duration:
            raise ValueError("heartbeat_interval must be positive and shorter than lease_duration")
        self.scheduler = scheduler
        self.journal = journal
        self.worker_id = worker_id
        self.lease_duration = lease_duration
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.heartbeat_interval = interval
        self._stop = Event()

    def process_once(self) -> WorkerResult | None:
        work = self.scheduler.claim(self.worker_id, lease_duration=self.lease_duration)
        if work is None:
            return None
        if work.lease_token is None:
            raise RuntimeError(f"claimed work item {work.work_id} has no lease token")

        lease_lost = Event()
        heartbeat_stop = Event()
        heartbeat = Thread(
            target=self._heartbeat,
            args=(work.work_id, work.lease_token, heartbeat_stop, lease_lost),
            daemon=True,
        )
        heartbeat.start()
        try:
            event = self.journal.load_event(work.event_id)
            self._validate_authoritative_event(event, work)
            if lease_lost.is_set():
                raise RuntimeError("worker lease was lost before event append")

            result = self.journal.append(event)
            inserted = getattr(result, "inserted", None)
            if inserted not in (True, False):
                raise RuntimeError("event journal append returned an invalid result")
            if not self.scheduler.complete(work.work_id, self.worker_id, work.lease_token):
                raise RuntimeError("worker lease was lost before completion")
            return WorkerResult(
                work_id=work.work_id,
                event_id=work.event_id,
                completed=True,
                appended=inserted,
            )
        except Exception as exc:
            self._record_failure(work, exc)
            raise
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=max(self.heartbeat_interval.total_seconds(), 0.1))

    def _heartbeat(self, work_id: UUID, lease_token: UUID, stop: Event, lease_lost: Event) -> None:
        while not stop.wait(self.heartbeat_interval.total_seconds()):
            try:
                renewed = self.scheduler.renew(
                    work_id,
                    self.worker_id,
                    lease_token,
                    lease_duration=self.lease_duration,
                )
            except Exception:
                lease_lost.set()
                return
            if not renewed:
                lease_lost.set()
                return

    def _record_failure(self, work: WorkItem, exc: Exception) -> None:
        try:
            self.scheduler.fail(
                work.work_id,
                self.worker_id,
                work.lease_token,
                str(exc),
                retry_at=datetime.now(timezone.utc) + self.retry_delay,
                max_attempts=self.max_attempts,
            )
        except Exception:
            # Preserve the primary processing failure. If failure recording is
            # unavailable, lease expiry remains the durable recovery mechanism.
            return

    @staticmethod
    def _validate_authoritative_event(event: Any, work: WorkItem) -> None:
        if event is None:
            raise RuntimeError(f"authoritative event {work.event_id} was not found")
        for field in ("event_id", "tenant_id", "aggregate_id", "run_id"):
            if getattr(event, field, None) != getattr(work, field):
                raise RuntimeError(f"authoritative event {field} does not match work item")

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
    max_attempts: int = 3,
    retry_delay: timedelta = timedelta(seconds=1),
    heartbeat_interval: timedelta | None = None,
) -> RuntimeWorker:
    return RuntimeWorker(
        scheduler=scheduler,
        journal=journal,
        worker_id=worker_id,
        lease_duration=lease_duration,
        max_attempts=max_attempts,
        retry_delay=retry_delay,
        heartbeat_interval=heartbeat_interval,
    )
