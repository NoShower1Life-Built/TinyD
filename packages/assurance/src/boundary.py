from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from contracts import EvidenceVerifier, EvidenceWriter, PolicyEngine, VerificationResult
from events import EventEnvelope


@dataclass(frozen=True)
class AssuranceReceipt:
    policy_decision: Any
    evidence_receipt: Any
    verification: VerificationResult


class AssuredExecutionBoundary:
    """Single in-process integration point: authorize, record, then independently verify."""
    def __init__(self, policy: PolicyEngine, writer: EvidenceWriter, verifier: EvidenceVerifier) -> None:
        self.policy = policy
        self.writer = writer
        self.verifier = verifier

    def authorize_record_verify(self, request: Mapping[str, Any], event: EventEnvelope, policy_version: str) -> AssuranceReceipt:
        decision = self.policy.evaluate(request, policy_version)
        if decision.decision != "ALLOW":
            raise PermissionError(f"execution denied: {decision.reason}")
        if event.tenant_id != str(request["tenant_id"]):
            raise PermissionError("tenant boundary violation")
        if event.policy_version != decision.policy_version or event.policy_digest != decision.policy_digest:
            raise ValueError("event policy binding does not match authorization decision")
        receipt = self.writer.append(event)
        verification = self.verifier.verify(event)
        if verification.result != "VERIFIED":
            raise ValueError("evidence verification failed")
        return AssuranceReceipt(decision, receipt, verification)
