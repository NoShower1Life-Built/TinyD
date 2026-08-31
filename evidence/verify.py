from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .predicates import evaluate
from .types import EvidenceRecord, VerificationClaim
from execution import ExecutionLedger, ExecutionState


@dataclass(frozen=True)
class VerificationResult:
    claim: VerificationClaim
    state: str


class VerificationEngine:
    """Verify requirements only from successful, current, predicate-satisfying executions."""

    def __init__(self, execution_ledger: ExecutionLedger | None = None) -> None:
        self.execution_ledger = execution_ledger

    def verify(self, requirement_id: str, evidence: list[EvidenceRecord], current_source_revision: str, predicates: list[dict[str, Any]] | None = None) -> VerificationResult:
        relevant = [e for e in evidence if e.requirement_id == requirement_id]
        current = [e for e in relevant if e.source_revision == current_source_revision]
        if not relevant:
            return self._result(requirement_id, (), current_source_revision, False, "no evidence", "INVALID")
        valid: list[EvidenceRecord] = []
        for item in current:
            if not item.execution_id or not item.payload:
                continue
            if self.execution_ledger is not None:
                execution = self.execution_ledger.get(item.execution_id)
                if execution is None or execution.state is not ExecutionState.SUCCEEDED or execution.source_revision != current_source_revision:
                    continue
            if predicates and not all(evaluate(p, item.payload) for p in predicates):
                continue
            valid.append(item)
        if not current:
            return self._result(requirement_id, tuple(e.evidence_id for e in relevant), current_source_revision, False, "evidence is stale", "STALE")
        if not valid:
            return self._result(requirement_id, tuple(e.evidence_id for e in current), current_source_revision, False, "no current evidence satisfies execution and predicates", "INVALID")
        return self._result(requirement_id, tuple(e.evidence_id for e in valid), current_source_revision, True, "current evidence is execution-bound and satisfies required predicates", "VERIFIED")

    @staticmethod
    def _result(requirement_id: str, ids: tuple[str, ...], revision: str, verified: bool, reason: str, state: str) -> VerificationResult:
        digest = hashlib.sha256((requirement_id + ":" + ":".join(ids) + ":" + revision).encode()).hexdigest()[:24]
        return VerificationResult(VerificationClaim("ver-" + digest, requirement_id, ids, revision, verified, reason), state)
