from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .types import EvidenceRecord, VerificationClaim


@dataclass(frozen=True)
class VerificationResult:
    claim: VerificationClaim
    state: str


class VerificationEngine:
    """Verify claims only when evidence exists, is execution-bound, and matches source."""

    def verify(
        self,
        requirement_id: str,
        evidence: list[EvidenceRecord],
        current_source_revision: str,
    ) -> VerificationResult:
        relevant = [e for e in evidence if e.requirement_id == requirement_id]
        valid = [
            e for e in relevant
            if e.source_revision == current_source_revision and bool(e.execution_id) and bool(e.payload)
        ]
        evidence_ids = tuple(e.evidence_id for e in valid)
        digest = hashlib.sha256((requirement_id + ":" + ":".join(evidence_ids) + ":" + current_source_revision).encode()).hexdigest()[:24]
        verification_id = "ver-" + digest
        if not relevant:
            return VerificationResult(VerificationClaim(verification_id, requirement_id, (), current_source_revision, False, "no evidence"), "INVALID")
        if not valid:
            return VerificationResult(VerificationClaim(verification_id, requirement_id, tuple(e.evidence_id for e in relevant), current_source_revision, False, "evidence is stale or invalid"), "STALE")
        return VerificationResult(VerificationClaim(verification_id, requirement_id, evidence_ids, current_source_revision, True, "evidence is execution-bound and matches source revision"), "VERIFIED")
