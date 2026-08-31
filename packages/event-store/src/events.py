"""Canonical TinyD event/evidence primitives."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

SENSITIVE_KEYS = frozenset({"password", "secret", "token", "api_key", "apikey", "private_key", "credential"})


def contains_sensitive(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(k).lower() in SENSITIVE_KEYS or contains_sensitive(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_sensitive(v) for v in value)
    return False


def canonical_json(value: Any) -> str:
    if contains_sensitive(value):
        raise ValueError("secret-bearing value cannot enter canonical event data")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str; event_type: str; tenant_id: str; execution_id: str; actor: str; capability: str; operation: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_event_id: str | None = None; policy_id: str | None = None; policy_version: str | None = None
    policy_digest: str | None = None; code_digest: str | None = None; artifact_digest: str | None = None
    input_digest: str | None = None; output_digest: str | None = None; provenance_id: str | None = None
    idempotency_key: str | None = None; schema_version: str = "1.0"; integrity_digest: str = ""

    def canonical_body(self) -> dict[str, Any]:
        body = {"schema_version": self.schema_version, "event_id": self.event_id, "event_type": self.event_type,
            "tenant_id": self.tenant_id, "execution_id": self.execution_id, "actor": self.actor,
            "capability": self.capability, "operation": self.operation, "payload": self.payload,
            "timestamp": self.timestamp, "parent_event_id": self.parent_event_id, "policy_id": self.policy_id,
            "policy_version": self.policy_version, "policy_digest": self.policy_digest, "code_digest": self.code_digest,
            "artifact_digest": self.artifact_digest, "input_digest": self.input_digest, "output_digest": self.output_digest,
            "provenance_id": self.provenance_id, "idempotency_key": self.idempotency_key}
        canonical_json(body)
        return body

    def digest(self) -> str:
        return sha256(self.canonical_body())

    def with_integrity(self) -> "EventEnvelope":
        return EventEnvelope(**{**self.__dict__, "integrity_digest": self.digest()})

    def verify_integrity(self) -> bool:
        try:
            return bool(self.integrity_digest) and self.integrity_digest == self.digest()
        except ValueError:
            return False
