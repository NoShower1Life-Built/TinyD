from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def _mapping(event_type: EventType, aggregate_type: str, *identity_fields: str) -> AggregateMapping:
    return AggregateMapping(event_type, aggregate_type, identity_fields, ",".join(identity_fields))


_MAPPINGS: dict[EventType, AggregateMapping] = {
    event: _mapping(event, aggregate, field)
    for event, aggregate, field in (
        (EventType.AGENT_CREATED, "agent", "agent_id"),
        (EventType.AGENT_ENABLED, "agent", "agent_id"),
        (EventType.AGENT_DISABLED, "agent", "agent_id"),
        (EventType.RUN_REQUESTED, "run", "run_id"),
        (EventType.RUN_ACCEPTED, "run", "run_id"),
        (EventType.RUN_REJECTED, "run", "run_id"),
        (EventType.RUN_STARTED, "run", "run_id"),
        (EventType.RUN_PAUSED, "run", "run_id"),
        (EventType.RUN_RESUMED, "run", "run_id"),
        (EventType.RUN_CANCEL_REQUESTED, "run", "run_id"),
        (EventType.RUN_CANCELLED, "run", "run_id"),
        (EventType.RUN_COMPLETED, "run", "run_id"),
        (EventType.RUN_FAILED, "run", "run_id"),
        (EventType.PLAN_REQUESTED, "run", "run_id"),
        (EventType.PLAN_PROPOSED, "run", "run_id"),
        (EventType.PLAN_VALIDATED, "run", "run_id"),
        (EventType.PLAN_REJECTED, "run", "run_id"),
        (EventType.PLAN_COMMITTED, "run", "run_id"),
        (EventType.STEP_CREATED, "step", "step_id"),
        (EventType.STEP_READY, "step", "step_id"),
        (EventType.STEP_LEASED, "step", "step_id"),
        (EventType.STEP_STARTED, "step", "step_id"),
        (EventType.STEP_WAITING, "step", "step_id"),
        (EventType.STEP_RETRY_SCHEDULED, "step", "step_id"),
        (EventType.STEP_SUCCEEDED, "step", "step_id"),
        (EventType.STEP_FAILED, "step", "step_id"),
        (EventType.STEP_CANCELLED, "step", "step_id"),
        (EventType.CAPABILITY_AUTHORIZATION_REQUESTED, "step", "step_id"),
        (EventType.CAPABILITY_AUTHORIZED, "step", "step_id"),
        (EventType.CAPABILITY_DENIED, "step", "step_id"),
        (EventType.CAPABILITY_INVOCATION_REQUESTED, "step", "step_id"),
        (EventType.CAPABILITY_INVOCATION_STARTED, "step", "step_id"),
        (EventType.CAPABILITY_INVOCATION_SUCCEEDED, "step", "step_id"),
        (EventType.CAPABILITY_INVOCATION_FAILED, "step", "step_id"),
        (EventType.MODEL_REQUESTED, "step", "step_id"),
        (EventType.MODEL_STARTED, "step", "step_id"),
        (EventType.MODEL_COMPLETED, "step", "step_id"),
        (EventType.MODEL_FAILED, "step", "step_id"),
        (EventType.MEMORY_READ_REQUESTED, "agent", "agent_id"),
        (EventType.MEMORY_READ_COMPLETED, "agent", "agent_id"),
        (EventType.MEMORY_WRITE_REQUESTED, "agent", "agent_id"),
        (EventType.MEMORY_WRITE_COMMITTED, "agent", "agent_id"),
        (EventType.MEMORY_WRITE_REJECTED, "agent", "agent_id"),
        (EventType.VERIFICATION_REQUESTED, "run", "run_id"),
        (EventType.VERIFICATION_STARTED, "run", "run_id"),
        (EventType.VERIFICATION_PASSED, "run", "run_id"),
        (EventType.VERIFICATION_FAILED, "run", "run_id"),
        (EventType.VERIFICATION_INCONCLUSIVE, "run", "run_id"),
        (EventType.ARTIFACT_BOUND, "artifact", "artifact_id"),
        (EventType.ARTIFACT_PRODUCED, "artifact", "artifact_id"),
        (EventType.ARTIFACT_DIGEST_RECORDED, "artifact", "artifact_id"),
        (EventType.PROVENANCE_RECORDED, "artifact", "artifact_id"),
        (EventType.APPROVAL_REQUESTED, "run", "run_id"),
        (EventType.APPROVAL_GRANTED, "run", "run_id"),
        (EventType.APPROVAL_DENIED, "run", "run_id"),
    )
}

_MAPPINGS.update(
    {
        EventType.LEGACY_WORKFLOW_REQUESTED: _mapping(
            EventType.LEGACY_WORKFLOW_REQUESTED, "workflow", "workflow"
        ),
        EventType.LEGACY_WORKFLOW_REPLAYED: _mapping(
            EventType.LEGACY_WORKFLOW_REPLAYED, "workflow", "workflow"
        ),
        EventType.LEGACY_MARKETPLACE_PACKAGE_INSTALLED: _mapping(
            EventType.LEGACY_MARKETPLACE_PACKAGE_INSTALLED,
            "marketplace_package",
            "package_id",
            "version",
        ),
        EventType.LEGACY_MARKETPLACE_USAGE_RECORDED: _mapping(
            EventType.LEGACY_MARKETPLACE_USAGE_RECORDED,
            "marketplace_usage",
            "package_id",
        ),
        EventType.LEGACY_BILLING_WEBHOOK_RECEIVED: _mapping(
            EventType.LEGACY_BILLING_WEBHOOK_RECEIVED, "billing", "tenant_id"
        ),
        EventType.LEGACY_BILLING_CUSTOMER_LINKED: _mapping(
            EventType.LEGACY_BILLING_CUSTOMER_LINKED, "billing", "tenant_id"
        ),
    }
)


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
