from enum import StrEnum
from typing import NamedTuple


class EventType(StrEnum):
    AGENT_CREATED = "agent.created"
    AGENT_ENABLED = "agent.enabled"
    AGENT_DISABLED = "agent.disabled"
    RUN_REQUESTED = "run.requested"
    RUN_ACCEPTED = "run.accepted"
    RUN_REJECTED = "run.rejected"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_CANCEL_REQUESTED = "run.cancel_requested"
    RUN_CANCELLED = "run.cancelled"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    PLAN_REQUESTED = "plan.requested"
    PLAN_PROPOSED = "plan.proposed"
    PLAN_VALIDATED = "plan.validated"
    PLAN_REJECTED = "plan.rejected"
    PLAN_COMMITTED = "plan.committed"
    STEP_CREATED = "step.created"
    STEP_READY = "step.ready"
    STEP_LEASED = "step.leased"
    STEP_STARTED = "step.started"
    STEP_WAITING = "step.waiting"
    STEP_RETRY_SCHEDULED = "step.retry_scheduled"
    STEP_SUCCEEDED = "step.succeeded"
    STEP_FAILED = "step.failed"
    STEP_CANCELLED = "step.cancelled"
    CAPABILITY_AUTHORIZATION_REQUESTED = "capability.authorization_requested"
    CAPABILITY_AUTHORIZED = "capability.authorized"
    CAPABILITY_DENIED = "capability.denied"
    CAPABILITY_INVOCATION_REQUESTED = "capability.invocation_requested"
    CAPABILITY_INVOCATION_STARTED = "capability.invocation_started"
    CAPABILITY_INVOCATION_SUCCEEDED = "capability.invocation_succeeded"
    CAPABILITY_INVOCATION_FAILED = "capability.invocation_failed"
    MODEL_REQUESTED = "model.requested"
    MODEL_STARTED = "model.started"
    MODEL_COMPLETED = "model.completed"
    MODEL_FAILED = "model.failed"
    MEMORY_READ_REQUESTED = "memory.read_requested"
    MEMORY_READ_COMPLETED = "memory.read_completed"
    MEMORY_WRITE_REQUESTED = "memory.write_requested"
    MEMORY_WRITE_COMMITTED = "memory.write_committed"
    MEMORY_WRITE_REJECTED = "memory.write_rejected"
    VERIFICATION_REQUESTED = "verification.requested"
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    VERIFICATION_INCONCLUSIVE = "verification.inconclusive"
    ARTIFACT_BOUND = "artifact.bound"
    ARTIFACT_PRODUCED = "artifact.produced"
    ARTIFACT_DIGEST_RECORDED = "artifact.digest_recorded"
    PROVENANCE_RECORDED = "provenance.recorded"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    LEGACY_WORKFLOW_REQUESTED = "workflow.requested"
    LEGACY_WORKFLOW_REPLAYED = "workflow.replayed"
    LEGACY_MARKETPLACE_PACKAGE_INSTALLED = "marketplace.package.installed"
    LEGACY_MARKETPLACE_USAGE_RECORDED = "marketplace.usage.recorded"
    LEGACY_BILLING_WEBHOOK_RECEIVED = "billing.webhook.received"
    LEGACY_BILLING_CUSTOMER_LINKED = "billing.customer.linked"


class EventRegistration(NamedTuple):
    event_type: EventType
    version: int
    aggregate_type: str


_PREFIX_TO_AGGREGATE = {
    "agent": "agent",
    "run": "run",
    "plan": "run",
    "step": "step",
    "capability": "step",
    "model": "step",
    "memory": "agent",
    "verification": "run",
    "artifact": "artifact",
    "provenance": "artifact",
    "approval": "run",
}

_LEGACY_AGGREGATES = {
    EventType.LEGACY_WORKFLOW_REQUESTED: "workflow",
    EventType.LEGACY_WORKFLOW_REPLAYED: "workflow",
    EventType.LEGACY_MARKETPLACE_PACKAGE_INSTALLED: "marketplace_package",
    EventType.LEGACY_MARKETPLACE_USAGE_RECORDED: "marketplace_usage",
    EventType.LEGACY_BILLING_WEBHOOK_RECEIVED: "billing",
    EventType.LEGACY_BILLING_CUSTOMER_LINKED: "billing",
}


def _registration(event: EventType) -> EventRegistration:
    aggregate_type = _LEGACY_AGGREGATES.get(event)
    if aggregate_type is None:
        prefix = event.value.split(".", 1)[0]
        aggregate_type = _PREFIX_TO_AGGREGATE[prefix]
    return EventRegistration(event, 1, aggregate_type)


EVENT_REGISTRY: dict[EventType, EventRegistration] = {
    event: _registration(event) for event in EventType
}
