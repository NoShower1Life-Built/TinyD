from enum import StrEnum

from .events import EventType


class RunState(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
    WAITING = "waiting"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class StepState(StrEnum):
    CREATED = "created"
    READY = "ready"
    LEASED = "leased"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_RUN_TRANSITIONS: dict[tuple[RunState, EventType], RunState] = {
    (RunState.REQUESTED, EventType.RUN_ACCEPTED): RunState.ACCEPTED,
    (RunState.REQUESTED, EventType.RUN_REJECTED): RunState.REJECTED,
    (RunState.ACCEPTED, EventType.PLAN_REQUESTED): RunState.PLANNING,
    (RunState.PLANNING, EventType.PLAN_COMMITTED): RunState.READY,
    (RunState.READY, EventType.RUN_STARTED): RunState.EXECUTING,
    (RunState.EXECUTING, EventType.RUN_PAUSED): RunState.WAITING,
    (RunState.WAITING, EventType.RUN_RESUMED): RunState.EXECUTING,
    (RunState.EXECUTING, EventType.VERIFICATION_REQUESTED): RunState.VERIFYING,
    (RunState.VERIFYING, EventType.VERIFICATION_PASSED): RunState.COMPLETED,
    (RunState.VERIFYING, EventType.VERIFICATION_FAILED): RunState.FAILED,
    (RunState.EXECUTING, EventType.RUN_COMPLETED): RunState.COMPLETED,
    (RunState.EXECUTING, EventType.RUN_FAILED): RunState.FAILED,
    (RunState.ACCEPTED, EventType.RUN_CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.READY, EventType.RUN_CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.EXECUTING, EventType.RUN_CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.WAITING, EventType.RUN_CANCEL_REQUESTED): RunState.CANCEL_REQUESTED,
    (RunState.CANCEL_REQUESTED, EventType.RUN_CANCELLED): RunState.CANCELLED,
}

_STEP_TRANSITIONS: dict[tuple[StepState, EventType], StepState] = {
    (StepState.CREATED, EventType.STEP_READY): StepState.READY,
    (StepState.READY, EventType.STEP_LEASED): StepState.LEASED,
    (StepState.LEASED, EventType.STEP_STARTED): StepState.RUNNING,
    (StepState.RUNNING, EventType.STEP_WAITING): StepState.WAITING,
    (StepState.WAITING, EventType.STEP_READY): StepState.READY,
    (StepState.RUNNING, EventType.STEP_SUCCEEDED): StepState.SUCCEEDED,
    (StepState.RUNNING, EventType.STEP_FAILED): StepState.FAILED,
    (StepState.FAILED, EventType.STEP_RETRY_SCHEDULED): StepState.RETRYING,
    (StepState.RETRYING, EventType.STEP_READY): StepState.READY,
    (StepState.READY, EventType.STEP_CANCELLED): StepState.CANCELLED,
    (StepState.LEASED, EventType.STEP_CANCELLED): StepState.CANCELLED,
    (StepState.RUNNING, EventType.STEP_CANCELLED): StepState.CANCELLED,
    (StepState.WAITING, EventType.STEP_CANCELLED): StepState.CANCELLED,
}


def transition_run(current: RunState, event: EventType) -> RunState:
    try:
        return _RUN_TRANSITIONS[(current, event)]
    except KeyError as exc:
        raise ValueError(f"invalid run transition: {current} + {event}") from exc


def transition_step(current: StepState, event: EventType) -> StepState:
    try:
        return _STEP_TRANSITIONS[(current, event)]
    except KeyError as exc:
        raise ValueError(f"invalid step transition: {current} + {event}") from exc
