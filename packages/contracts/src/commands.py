from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthorizationContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subject_id: UUID
    permissions: frozenset[str] = frozenset()
    policy_version: str


class CommandEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    command_type: str
    tenant_id: UUID
    agent_id: UUID
    aggregate_id: UUID
    correlation_id: UUID
    causation_id: UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=512)
    requested_by: UUID
    authorization: AuthorizationContext
    payload: dict[str, Any]


class SubmitRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    intent: str = Field(min_length=1)
    priority: int = Field(default=0, ge=0)


class ExecuteCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capability_id: str = Field(min_length=1)
    capability_version: int = Field(ge=1)
    input: dict[str, Any]


class RequestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_policy: str = Field(min_length=1)
    input: dict[str, Any]


class RequestVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subject_id: UUID
    verifier: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
