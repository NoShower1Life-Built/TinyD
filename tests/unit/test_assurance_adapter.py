from datetime import datetime, timezone

import pytest

from src.tinyd.assurance.adapter import AssuranceProjectionAdapter, ProjectionSourceError
from src.tinyd.assurance.projection import AssuranceRequirement, AssuranceStatus

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
REQ = AssuranceRequirement("req-1", "tenant-a", "policy-v1", "impl-1", "test-1")


def source(tenant, requirement):
    return {
        "tenant_id": tenant,
        "implementation": {"tenant_id": tenant, "attested": True},
        "test": {"tenant_id": tenant, "result": "PASS"},
        "execution": {"tenant_id": tenant, "execution_id": "exec-1", "result": "PASS"},
        "evidence": [{"tenant_id": tenant, "evidence_id": "ev-1", "integrity": "VERIFIED", "digest": "abc", "observed_at": NOW}],
        "provenance": [{"tenant_id": tenant, "provenance_id": "prov-1", "canonical": True}],
        "verification": [{"tenant_id": tenant, "verification_id": "ver-1", "result": "VERIFIED", "valid": True}],
        "replay": {"tenant_id": tenant, "verification_id": "replay-1", "result": "VERIFIED"},
        "trust_root": {"tenant_id": tenant, "trust_root_id": "root-1", "valid": True},
    }


def test_adapter_projects_authoritative_state():
    adapter = AssuranceProjectionAdapter(source)
    result = adapter.project(REQ, now=NOW)
    assert result.derived_status is AssuranceStatus.PROVEN
    assert result.execution_ref == "exec-1"
    assert result.evidence_refs == ("ev-1",)


def test_adapter_cannot_cross_tenant():
    adapter = AssuranceProjectionAdapter(lambda tenant, requirement: source("tenant-b", requirement))
    with pytest.raises(ProjectionSourceError):
        adapter.project(REQ, now=NOW)


def test_authoritative_missing_replay_cannot_become_proven():
    def missing_replay(tenant, requirement):
        data = source(tenant, requirement)
        data["replay"] = None
        return data

    result = AssuranceProjectionAdapter(missing_replay).project(REQ, now=NOW)
    assert result.derived_status is AssuranceStatus.UNPROVEN
