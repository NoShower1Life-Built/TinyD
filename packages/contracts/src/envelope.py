from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventIntegrity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    previous_digest: str | None = None
    digest: str


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    event_type: str
    event_version: int = Field(ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: UUID
    agent_id: UUID
    conversation_id: UUID | None = None
    run_id: UUID | None = None
    task_id: UUID | None = None
    step_id: UUID | None = None
    correlation_id: UUID
    causation_id: UUID | None = None
    aggregate_type: str
    aggregate_id: UUID
    sequence: int = Field(ge=1)
    producer: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    integrity: EventIntegrity
