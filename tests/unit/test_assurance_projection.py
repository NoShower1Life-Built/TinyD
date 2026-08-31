from datetime import datetime, timedelta, timezone

from src.tinyd.assurance.projection import (
    AssuranceRequirement,
    AssuranceStatus,
    project,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
REQ = AssuranceRequirement("req-1", "tenant-a", "policy-v1", "impl-1", "test-1")


def records(tenant="tenant-a"):
    return {
        "implementation": {"tenant_id": tenant, "attested": True},
        "test": {"tenant_id": tenant, "result": "PASS"},
        "execution": {"tenant_id": tenant, "execution_id": "exec-1", "result": "PASS"},
        "evidence": [{"tenant_id": tenant, "evidence_id": "ev-1", "integrity": "VERIFIED", "digest": "abc", "observed_at": NOW}],
        "provenance": [{"tenant_id": tenant, "provenance_id": "prov-1", "canonical": True}],
        "verification": [{"tenant_id": tenant, "verification_id": "ver-1", "result": "VERIFIED", "valid": True}],
        "replay": {"tenant_id": tenant, "verification_id": "replay-1", "result": "VERIFIED"},
        "trust_root": {"tenant_id": tenant, "trust_root_id": "root-1", "valid": True},
    }


def make(**overrides):
    r = records()
    r.update(overrides)
    return project(REQ, now=NOW, **r)


def test_complete_chain_is_proven():
    assert make().derived_status is AssuranceStatus.PROVEN


def test_missing_evidence_is_unproven():
    assert make(evidence=[]).derived_status is AssuranceStatus.UNPROVEN


def test_missing_replay_is_unproven():
    assert make(replay=None).derived_status is AssuranceStatus.UNPROVEN


def test_cross_tenant_evidence_fails():
    assert make(evidence=[{"tenant_id": "tenant-b", "evidence_id": "ev-1", "integrity": "VERIFIED", "digest": "abc", "observed_at": NOW}]).derived_status is AssuranceStatus.FAILED


def test_revoked_evidence_fails():
    assert make(evidence=[{"tenant_id": "tenant-a", "evidence_id": "ev-1", "integrity": "VERIFIED", "digest": "abc", "observed_at": NOW, "revoked": True}]).derived_status is AssuranceStatus.FAILED


def test_stale_evidence_is_unproven():
    old = NOW - timedelta(days=2)
    assert make(evidence=[{"tenant_id": "tenant-a", "evidence_id": "ev-1", "integrity": "VERIFIED", "digest": "abc", "observed_at": old}]).derived_status is AssuranceStatus.UNPROVEN


def test_secret_never_becomes_proven():
    assert make(evidence=[{"tenant_id": "tenant-a", "evidence_id": "ev-1", "integrity": "VERIFIED", "digest": "abc", "observed_at": NOW, "secret_present": True}]).derived_status is AssuranceStatus.FAILED


def test_unverified_replay_is_unproven():
    assert make(replay={"tenant_id": "tenant-a", "verification_id": "replay-1", "result": "FAILED"}).derived_status is AssuranceStatus.UNPROVEN
