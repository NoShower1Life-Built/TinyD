"""Canonical assurance contracts; implementations remain in-process."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from events import EventEnvelope

@dataclass(frozen=True)
class PolicyDecision:
    decision: str; policy_id: str; policy_version: str; policy_digest: str; context_digest: str; reason: str

@dataclass(frozen=True)
class EvidenceReceipt:
    evidence_id: str; evidence_digest: str; sequence: int

@dataclass(frozen=True)
class VerificationResult:
    verification_id: str; subject_digest: str; result: str; verifier_id: str; verifier_version: str; verification_digest: str; reason: str = ""

@dataclass(frozen=True)
class Attestation:
    artifact_digest: str; attestation_digest: str; signer_id: str; key_version: str; algorithm: str; signature_b64: str

class PolicyEngine(Protocol):
    def evaluate(self, request: Mapping[str, Any], policy_version: str) -> PolicyDecision: ...
class EvidenceWriter(Protocol):
    def append(self, event: EventEnvelope) -> EvidenceReceipt: ...
class EvidenceVerifier(Protocol):
    def verify(self, event: EventEnvelope) -> VerificationResult: ...
class ProvenanceResolver(Protocol):
    def resolve(self, subject_id: str) -> Mapping[str, Any]: ...
class IntegrityVerifier(Protocol):
    def verify(self, event: EventEnvelope) -> bool: ...
class ArtifactAttestor(Protocol):
    def attest(self, artifact_digest: str) -> Attestation: ...
class OwnershipRegistry(Protocol):
    def record(self, tenant_id: str, subject_id: str, relationship: str, target_id: str) -> Any: ...
    def get(self, tenant_id: str, subject_id: str, relationship: str, target_id: str) -> Any: ...
class ReplayVerifier(Protocol):
    def replay(self, execution_id: str, events: Sequence[EventEnvelope]) -> VerificationResult: ...
