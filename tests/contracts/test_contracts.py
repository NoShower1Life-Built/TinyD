from uuid import uuid4

import pytest

from packages.contracts.src.envelope import EventEnvelope, EventIntegrity
from packages.contracts.src.events import EventType, EVENT_REGISTRY
from packages.contracts.src.execution import RunState, StepState, transition_run, transition_step


def test_event_envelope_requires_versioned_integrity_and_tenant_context() -> None:
    event = EventEnvelope(
        event_id=uuid4(),
        event_type=EventType.RUN_REQUESTED,
        event_version=1,
        tenant_id=uuid4(),
        agent_id=uuid4(),
        correlation_id=uuid4(),
        aggregate_type="run",
        aggregate_id=uuid4(),
        sequence=1,
        producer="tinyd-agent",
        payload={"intent": "test"},
        integrity=EventIntegrity(digest="sha256:test"),
    )
    assert event.event_type == EventType.RUN_REQUESTED
    assert event.event_version == 1


def test_event_registry_contains_every_event_type() -> None:
    assert set(EVENT_REGISTRY) == set(EventType)
    assert all(registration.version == 1 for registration in EVENT_REGISTRY.values())


def test_valid_run_transition() -> None:
    assert transition_run(RunState.REQUESTED, EventType.RUN_ACCEPTED) == RunState.ACCEPTED
    assert transition_run(RunState.ACCEPTED, EventType.PLAN_REQUESTED) == RunState.PLANNING
    assert transition_run(RunState.PLANNING, EventType.PLAN_COMMITTED) == RunState.READY
    assert transition_run(RunState.READY, EventType.RUN_STARTED) == RunState.EXECUTING


def test_invalid_run_transition_fails_closed() -> None:
    with pytest.raises(ValueError, match="invalid run transition"):
        transition_run(RunState.COMPLETED, EventType.RUN_STARTED)


def test_valid_step_transition() -> None:
    assert transition_step(StepState.CREATED, EventType.STEP_READY) == StepState.READY
    assert transition_step(StepState.READY, EventType.STEP_LEASED) == StepState.LEASED
    assert transition_step(StepState.LEASED, EventType.STEP_STARTED) == StepState.RUNNING
    assert transition_step(StepState.RUNNING, EventType.STEP_SUCCEEDED) == StepState.SUCCEEDED


def test_invalid_step_transition_fails_closed() -> None:
    with pytest.raises(ValueError, match="invalid step transition"):
        transition_step(StepState.SUCCEEDED, EventType.STEP_STARTED)
