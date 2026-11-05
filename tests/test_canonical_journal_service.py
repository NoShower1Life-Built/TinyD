import os
from uuid import uuid4

import pytest

from packages.runtime.src.journal import PostgresEventJournal
from packages.runtime.src.journal_service import append_tenant_event


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL canonical-journal tests",
)


def test_append_assigns_sequence_and_hash_chain():
    journal = PostgresEventJournal(os.environ["DATABASE_URL"])
    tenant_id = uuid4()
    aggregate_id = uuid4()

    first = append_tenant_event(
        journal,
        tenant_id=tenant_id,
        event_type="build_lint.analysis.requested",
        aggregate_type="build_lint_analysis",
        aggregate_id=aggregate_id,
        payload={"repository": "example/repository", "revision": "a" * 40},
    )
    second = append_tenant_event(
        journal,
        tenant_id=tenant_id,
        event_type="build_lint.analysis.started",
        aggregate_type="build_lint_analysis",
        aggregate_id=aggregate_id,
        payload={"worker_id": "worker-1"},
    )

    assert first.sequence == 1
    assert first.integrity.previous_digest is None
    assert second.sequence == 2
    assert second.integrity.previous_digest == first.integrity.digest
    assert second.integrity.digest == journal.calculate_digest(
        second, first.integrity.digest
    )
    assert [event.event_id for event in journal.history(
        tenant_id, "build_lint_analysis", aggregate_id
    )] == [first.event_id, second.event_id]


def test_append_same_event_id_is_idempotent():
    journal = PostgresEventJournal(os.environ["DATABASE_URL"])
    tenant_id = uuid4()
    aggregate_id = uuid4()
    event_id = uuid4()
    payload = {"repository": "example/repository", "revision": "b" * 40}

    first = append_tenant_event(
        journal,
        tenant_id=tenant_id,
        event_type="build_lint.analysis.requested",
        aggregate_type="build_lint_analysis",
        aggregate_id=aggregate_id,
        payload=payload,
        event_id=event_id,
    )
    repeated = append_tenant_event(
        journal,
        tenant_id=tenant_id,
        event_type="build_lint.analysis.requested",
        aggregate_type="build_lint_analysis",
        aggregate_id=aggregate_id,
        payload=payload,
        event_id=event_id,
    )

    assert repeated.event_id == first.event_id
    assert repeated.sequence == first.sequence
    assert repeated.integrity.digest == first.integrity.digest
