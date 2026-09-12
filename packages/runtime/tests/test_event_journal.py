from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.event_journal import EventJournal


@dataclass(frozen=True)
class Result:
    inserted: bool


class Store:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)
        return Result(inserted=True)

    def read(self, tenant_id, aggregate_id, run_id):
        return tuple(self.events)


@dataclass(frozen=True)
class Event:
    event_id: str
    tenant_id: str = "tenant-1"
    aggregate_id: str = "aggregate-1"
    run_id: str = "run-1"


def test_runtime_journal_delegates_append_to_authoritative_store():
    store = Store()
    journal = EventJournal(store)
    event = Event("evt-1")
    result = journal.append(event)
    assert result.inserted is True
    assert store.events == [event]


def test_runtime_journal_loads_authoritative_stream():
    store = Store()
    journal = EventJournal(store)
    event = Event("evt-1")
    store.events.append(event)
    assert journal.load("tenant-1", "aggregate-1", "run-1") == (event,)
