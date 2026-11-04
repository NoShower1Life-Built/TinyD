from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SideEffectClass(StrEnum):
    PURE = "pure"
    READ_ONLY = "read_only"
    EXTERNAL_READ = "external_read"
    EXTERNAL_WRITE = "external_write"
    MUTATING = "mutating"
    PRIVILEGED = "privileged"


class CapabilityDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capability_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    side_effect_class: SideEffectClass
    required_permissions: frozenset[str] = frozenset()
    tenant_scoped: bool = True
    timeout_seconds: float = Field(gt=0)
    verification_required: bool = True
