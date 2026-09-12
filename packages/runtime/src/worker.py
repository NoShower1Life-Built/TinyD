from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any

try:
    from .event_journal import EventJournal
except ImportError:
    from event_journal import EventJournal


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    event: Any


class RuntimeScheduler:
    """Deterministic in-process scheduler that hands work to a worker queue."""

    def __init__(self) -> None:
        self._queue: Queue[ScheduledEvent] = Queue()

    def submit(self, event: Any) -> None:
        self._queue.put(ScheduledEvent(event=event))

    def get(self, timeout: float | None = None) -> ScheduledEvent:
        return self._queue.get(timeout=timeout)

    def task_done(self) -> None:
        self._queue.task_done()


class RuntimeWorker:
    """Worker whose authoritative persistence boundary is EventJournal."""

    def __init__(self, scheduler: RuntimeScheduler, journal: EventJournal) -> None:
        self.scheduler = scheduler
        self.journal = journal
        self._stop = Event()

    def process_once(self, timeout: float | None = None) -> Any:
        item = self.scheduler.get(timeout=timeout)
        try:
            return self.journal.append(item.event)
        finally:
            self.scheduler.task_done()

    def run(self, timeout: float = 0.5) -> None:
        while not self._stop.is_set():
            try:
                self.process_once(timeout=timeout)
            except Empty:
                continue
            except Exception:
                if self._stop.is_set():
                    break
                raise

    def start(self, timeout: float = 0.5) -> Thread:
        thread = Thread(target=self.run, kwargs={"timeout": timeout}, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()


def build_worker(journal: EventJournal) -> tuple[RuntimeScheduler, RuntimeWorker]:
    scheduler = RuntimeScheduler()
    return scheduler, RuntimeWorker(scheduler=scheduler, journal=journal)
