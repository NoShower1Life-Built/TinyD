from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from packages.contracts.src.events import EventType


MAPPING_VERSION = 1


class EventMappingError(ValueError):
    """Raised when a legacy event cannot be mapped deterministically."""


@dataclass(frozen=True)
class AggregateMapping:
    event_type: EventType
    aggregate_type: str
    identity_fields: tuple[str, ...]
    identity_label: str

    def identity(self, event: dict[str, Any]) -> str:
        values: list[str] = []
        for field in self.identity_fields:
            value = event.get(field)
            if value is None and isinstance(event.get("payload"), dict):
                value = event["payload"].get(field)
            if value is None or str(value).strip() == "":
                raise EventMappingError(
                    f"{self.event_type.value} requires aggregate identity field {field!r}"
                )
            values.append(str(value).strip())
        return "\x1f".join(values)


_MAPPINGS: dict[EventType, AggregateMapping] = {
    EventType.RUN_REQUESTED: AggregateMapping(
        EventType.RUN_REQUESTED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_ACCEPTED: AggregateMapping(
        EventType.RUN_ACCEPTED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_REJECTED: AggregateMapping(
        EventType.RUN_REJECTED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_STARTED: AggregateMapping(
        EventType.RUN_STARTED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_PAUSED: AggregateMapping(
        EventType.RUN_PAUSED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_RESUMED: AggregateMapping(
        EventType.RUN_RESUMED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_CANCEL_REQUESTED: AggregateMapping(
        EventType.RUN_CANCEL_REQUESTED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_CANCELLED: AggregateMapping(
        EventType.RUN_CANCELLED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_COMPLETED: AggregateMapping(
        EventType.RUN_COMPLETED, "run", ("run_id",), "run_id"
    ),
    EventType.RUN_FAILED: AggregateMapping(
        EventType.RUN_FAILED, "run", ("run_id",), "run_id"
    ),
    EventType.PLAN_REQUESTED: AggregateMapping(
        EventType.PLAN_REQUESTED, "run", ("run_id",), "run_id"
    ),
    EventType.PLAN_PROPOSED: AggregateMapping(
        EventType.PLAN_PROPOSED, "run", ("run_id",), "run_id"
    ),
    EventType.PLAN_VALIDATED: AggregateMapping(
        EventType.PLAN_VALIDATED, "run", ("run_id",), "run_id"
    ),
    EventType.PLAN_REJECTED: AggregateMapping(
        EventType.PLAN_REJECTED, "run", ("run_id",), "run_id"
    ),
    EventType.PLAN_COMMITTED: AggregateMapping(
        EventType.PLAN_COMMITTED, "run", ("run_id",), "run_id"
    ),
    EventType.STEP_CREATED: AggregateMapping(
        EventType.STEP_CREATED, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_READY: AggregateMapping(
        EventType.STEP_READY, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_LEASED: AggregateMapping(
        EventType.STEP_LEASED, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_STARTED: AggregateMapping(
        EventType.STEP_STARTED, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_WAITING: AggregateMapping(
        EventType.STEP_WAITING, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_RETRY_SCHEDULED: AggregateMapping(
        EventType.STEP_RETRY_SCHEDULED, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_SUCCEEDED: AggregateMapping(
        EventType.STEP_SUCCEEDED, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_FAILED: AggregateMapping(
        EventType.STEP_FAILED, "step", ("step_id",), "step_id"
    ),
    EventType.STEP_CANCELLED: AggregateMapping(
        EventType.STEP_CANCELLED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_AUTHORIZATION_REQUESTED: AggregateMapping(
        EventType.CAPABILITY_AUTHORIZATION_REQUESTED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_AUTHORIZED: AggregateMapping(
        EventType.CAPABILITY_AUTHORIZED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_DENIED: AggregateMapping(
        EventType.CAPABILITY_DENIED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_INVOCATION_REQUESTED: AggregateMapping(
        EventType.CAPABILITY_INVOCATION_REQUESTED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_INVOCATION_STARTED: AggregateMapping(
        EventType.CAPABILITY_INVOCATION_STARTED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_INVOCATION_SUCCEEDED: AggregateMapping(
        EventType.CAPABILITY_INVOCATION_SUCCEEDED, "step", ("step_id",), "step_id"
    ),
    EventType.CAPABILITY_INVOCATION_FAILED: AggregateMapping(
        EventType.CAPABILITY_INVOCATION_FAILED, "step", ("step_id",), "step_id"
    ),
    EventType.MODEL_REQUESTED: AggregateMapping(
        EventType.MODEL_REQUESTED, "step", ("step_id",), "step_id"
    ),
    EventType.MODEL_STARTED: AggregateMapping(
        EventType.MODEL_STARTED, "step", ("step_id",), "step_id"
    ),
    EventType.MODEL_COMPLETED: AggregateMapping(
        EventType.MODEL_COMPLETED, "step", ("step_id",), "step_id"
    ),
    EventType.MODEL_FAILED: AggregateMapping(
        EventType.MODEL_FAILED, "step", ("step_id",), "step_id"
    ),
    EventType.MEMORY_READ_REQUESTED: AggregateMapping(
        EventType.MEMORY_READ_REQUESTED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.MEMORY_READ_COMPLETED: AggregateMapping(
        EventType.MEMORY_READ_COMPLETED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.MEMORY_WRITE_REQUESTED: AggregateMapping(
        EventType.MEMORY_WRITE_REQUESTED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.MEMORY_WRITE_COMMITTED: AggregateMapping(
        EventType.MEMORY_WRITE_COMMITTED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.MEMORY_WRITE_REJECTED: AggregateMapping(
        EventType.MEMORY_WRITE_REJECTED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.VERIFICATION_REQUESTED: AggregateMapping(
        EventType.VERIFICATION_REQUESTED, "run", ("run_id",), "run_id"
    ),
    EventType.VERIFICATION_STARTED: AggregateMapping(
        EventType.VERIFICATION_STARTED, "run", ("run_id",), "run_id"
    ),
    EventType.VERIFICATION_PASSED: AggregateMapping(
        EventType.VERIFICATION_PASSED, "run", ("run_id",), "run_id"
    ),
    EventType.VERIFICATION_FAILED: AggregateMapping(
        EventType.VERIFICATION_FAILED, "run", ("run_id",), "run_id"
    ),
    EventType.VERIFICATION_INCONCLUSIVE: AggregateMapping(
        EventType.VERIFICATION_INCONCLUSIVE, "run", ("run_id",), "run_id"
    ),
    EventType.ARTIFACT_BOUND: AggregateMapping(
        EventType.ARTIFACT_BOUND, "artifact", ("artifact_id",), "artifact_id"
    ),
    EventType.ARTIFACT_PRODUCED: AggregateMapping(
        EventType.ARTIFACT_PRODUCED, "artifact", ("artifact_id",), "artifact_id"
    ),
    EventType.ARTIFACT_DIGEST_RECORDED: AggregateMapping(
        EventType.ARTIFACT_DIGEST_RECORDED, "artifact", ("artifact_id",), "artifact_id"
    ),
    EventType.PROVENANCE_RECORDED: AggregateMapping(
        EventType.PROVENANCE_RECORDED, "artifact", ("artifact_id",), "artifact_id"
    ),
    EventType.APPROVAL_REQUESTED: AggregateMapping(
        EventType.APPROVAL_REQUESTED, "run", ("run_id",), "run_id"
    ),
    EventType.APPROVAL_GRANTED: AggregateMapping(
        EventType.APPROVAL_GRANTED, "run", ("run_id",), "run_id"
    ),
    EventType.APPROVAL_DENIED: AggregateMapping(
        EventType.APPROVAL_DENIED, "run", ("run_id",), "run_id"
    ),
    EventType.AGENT_CREATED: AggregateMapping(
        EventType.AGENT_CREATED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.AGENT_ENABLED: AggregateMapping(
        EventType.AGENT_ENABLED, "agent", ("agent_id",), "agent_id"
    ),
    EventType.AGENT_DISABLED: AggregateMapping(
        EventType.AGENT_DISABLED, "agent", ("agent_id",), "agent_id"
    ),
}


def get_mapping(event_type: str) -> AggregateMapping:
    try:
        parsed = EventType(event_type)
    except ValueError as exc:
        raise EventMappingError(f"unregistered event type: {event_type!r}") from exc
    try:
        return _MAPPINGS[parsed]
    except KeyError as exc:
        raise EventMappingError(f"no aggregate mapping for event type: {event_type!r}") from exc


def registered_event_types() -> tuple[str, ...]:
    return tuple(event.value for event in EventType)
