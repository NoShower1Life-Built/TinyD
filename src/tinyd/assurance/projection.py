"""Deterministic Scoreboard assurance projection.

This module is a projection only: it does not create execution truth. Callers
must supply authoritative event/evidence/verification records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable, Mapping


class AssuranceStatus(StrEnum):
    PROVEN = "PROVEN"
    FAILED = "FAILED"
    UNPROVEN = "UNPROVEN"
    HARDENING = "HARDENING"


@dataclass(frozen=True, slots=True)
class AssuranceRequirement:
    requirement_id: str
    tenant_id: str
    policy_version: str
    implementation_ref: str
    test_ref: str
    max_evidence_age_seconds: int = 86400


@dataclass(frozen=True, slots=True)
class AssuranceProjection:
    requirement_id: str
    tenant_id: str
    policy_version: str
    implementation_ref: str
    test_ref: str
    execution_ref: str | None
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]
    replay_verification_ref: str | None
    trust_root_ref: str | None
    derived_status: AssuranceStatus
    failure_reason: str | None
    derived_at: datetime


def _same_tenant(records: Iterable[Mapping[str, object]], tenant_id: str) -> bool:
    """Require explicit tenant identity on every authoritative record."""
    return all(record.get("tenant_id") == tenant_id for record in records)


def derive_status(
    requirement: AssuranceRequirement,
    *,
    implementation: Mapping[str, object] | None,
    test: Mapping[str, object] | None,
    execution: Mapping[str, object] | None,
    evidence: list[Mapping[str, object]],
    provenance: list[Mapping[str, object]],
    verification: list[Mapping[str, object]],
    replay: Mapping[str, object] | None,
    trust_root: Mapping[str, object] | None,
    now: datetime | None = None,
) -> AssuranceStatus:
    """Derive status without mutating or trusting the projection itself."""
    now = now or datetime.now(timezone.utc)
    records = [r for r in [implementation, test, execution, replay, trust_root] if r is not None]
    records.extend(evidence)
    records.extend(provenance)
    records.extend(verification)
    if not _same_tenant(records, requirement.tenant_id):
        return AssuranceStatus.FAILED

    if any(r.get("revoked") is True or r.get("valid") is False for r in evidence + verification):
        return AssuranceStatus.FAILED
    if implementation is None or test is None:
        return AssuranceStatus.UNPROVEN
    if execution is None or execution.get("result") != "PASS":
        return AssuranceStatus.UNPROVEN
    if not evidence or not provenance or not verification or replay is None or trust_root is None:
        return AssuranceStatus.UNPROVEN
    if test.get("result") != "PASS":
        return AssuranceStatus.FAILED
    if any(v.get("result") != "VERIFIED" for v in verification):
        return AssuranceStatus.UNPROVEN
    if replay.get("result") != "VERIFIED":
        return AssuranceStatus.UNPROVEN
    if trust_root.get("valid") is not True:
        return AssuranceStatus.UNPROVEN
    if implementation.get("attested") is not True:
        return AssuranceStatus.UNPROVEN
    if any(e.get("integrity") != "VERIFIED" for e in evidence):
        return AssuranceStatus.UNPROVEN
    if any(p.get("canonical") is not True for p in provenance):
        return AssuranceStatus.UNPROVEN

    for e in evidence:
        observed_at = e.get("observed_at")
        if not isinstance(observed_at, datetime):
            return AssuranceStatus.UNPROVEN
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        if (now - observed_at).total_seconds() > requirement.max_evidence_age_seconds:
            return AssuranceStatus.UNPROVEN
        if not e.get("digest"):
            return AssuranceStatus.UNPROVEN
        if e.get("secret_present") is True:
            return AssuranceStatus.FAILED

    return AssuranceStatus.PROVEN


def project(
    requirement: AssuranceRequirement,
    *,
    implementation: Mapping[str, object] | None,
    test: Mapping[str, object] | None,
    execution: Mapping[str, object] | None,
    evidence: list[Mapping[str, object]],
    provenance: list[Mapping[str, object]],
    verification: list[Mapping[str, object]],
    replay: Mapping[str, object] | None,
    trust_root: Mapping[str, object] | None,
    now: datetime | None = None,
) -> AssuranceProjection:
    status = derive_status(
        requirement,
        implementation=implementation,
        test=test,
        execution=execution,
        evidence=evidence,
        provenance=provenance,
        verification=verification,
        replay=replay,
        trust_root=trust_root,
        now=now,
    )
    return AssuranceProjection(
        requirement_id=requirement.requirement_id,
        tenant_id=requirement.tenant_id,
        policy_version=requirement.policy_version,
        implementation_ref=requirement.implementation_ref,
        test_ref=requirement.test_ref,
        execution_ref=execution.get("execution_id") if execution else None,
        evidence_refs=tuple(str(e["evidence_id"]) for e in evidence if "evidence_id" in e),
        provenance_refs=tuple(str(p["provenance_id"]) for p in provenance if "provenance_id" in p),
        verification_refs=tuple(str(v["verification_id"]) for v in verification if "verification_id" in v),
        replay_verification_ref=str(replay["verification_id"]) if replay and "verification_id" in replay else None,
        trust_root_ref=str(trust_root["trust_root_id"]) if trust_root and "trust_root_id" in trust_root else None,
        derived_status=status,
        failure_reason=None if status is not AssuranceStatus.FAILED else "assurance predicate failed",
        derived_at=now or datetime.now(timezone.utc),
    )
