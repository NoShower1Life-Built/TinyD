from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvidenceState(StrEnum):
    CAPTURED = "CAPTURED"
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    requirement_id: str
    execution_id: str
    source_revision: str
    kind: str
    payload: dict[str, Any]
    captured_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "requirementId": self.requirement_id,
            "executionId": self.execution_id,
            "sourceRevision": self.source_revision,
            "kind": self.kind,
            "payload": self.payload,
            "capturedAt": self.captured_at,
        }


@dataclass(frozen=True)
class VerificationClaim:
    verification_id: str
    requirement_id: str
    evidence_ids: tuple[str, ...]
    source_revision: str
    verified: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "verificationId": self.verification_id,
            "requirementId": self.requirement_id,
            "evidenceIds": list(self.evidence_ids),
            "sourceRevision": self.source_revision,
            "verified": self.verified,
            "reason": self.reason,
        }
