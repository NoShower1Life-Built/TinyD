from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from test_scheduler_integration import DurableScheduler, connection, make_event, persist_event, reset_schema


def test_complete_requires_lease_token():
    reset_schema()
    event = make_event("fence-complete")
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None
        with pytest.raises(TypeError):
            scheduler.complete(submitted.work_id, "worker-a")


def test_fail_requires_lease_token_and_explicit_error():
    reset_schema()
    event = make_event("fence-fail")
    persist_event(event)
    with connection() as conn:
        scheduler = DurableScheduler(conn)
        submitted = scheduler.submit(event)
        claimed = scheduler.claim("worker-a", lease_duration=timedelta(seconds=30))
        assert claimed is not None and claimed.lease_token is not None
        with pytest.raises(TypeError):
            scheduler.fail(submitted.work_id, "worker-a", "legacy error", retry_at=None, max_attempts=2)
        with pytest.raises(ValueError, match="lease_token"):
            scheduler.complete(submitted.work_id, "worker-a", UUID(int=0).hex)
