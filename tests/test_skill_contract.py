import copy
import pytest
from packages.tinyd_skills import SkillContractError, validate_manifest

VALID = {
    "contract_version": "1.0", "id": "repository-audit", "version": "1.0.0",
    "name": "Repository Audit",
    "purpose": "Inspect a repository and produce evidence-backed findings without modifying it.",
    "triggers": ["user requests repository audit", "user requests codebase risk review"],
    "inputs": [{"name": "repository", "type": "owner/repository", "required": True, "description": "Repository identifier."}],
    "outputs": [{"name": "findings", "type": "structured_report", "required": True, "description": "Findings with evidence and severity."}],
    "tools": ["github.read"],
    "permissions": {"read": ["repository", "pull_requests", "workflow_runs"], "write": [], "requires_approval": []},
    "risk": "low", "autonomy": "recommend",
    "workflow": [
        {"step": 1, "action": "Read repository metadata and current tree.", "success_condition": "Repository and ref are identified."},
        {"step": 2, "action": "Inspect relevant source, tests, and workflow configuration.", "success_condition": "Each finding references inspected evidence."},
        {"step": 3, "action": "Return prioritized findings and verification gaps.", "success_condition": "Report distinguishes observed, inferred, and unknown."}
    ],
    "failure_policy": {"retryable_errors": ["rate_limit", "transient_network"], "max_attempts": 3, "on_exhaustion": "escalate", "idempotency_key": "repository+ref+audit_version"},
    "verification": {"acceptance_criteria": ["Every finding includes evidence or is explicitly marked as an inference."], "evidence_required": ["repository_ref", "inspected_paths"], "independent_check": True}
}


def test_valid_manifest_returns_copy():
    result = validate_manifest(VALID)
    assert result == VALID and result is not VALID


@pytest.mark.parametrize("field", ["contract_version", "id", "version", "name", "purpose"])
def test_required_identity_fields_are_enforced(field):
    broken = copy.deepcopy(VALID)
    broken[field] = ""
    with pytest.raises(SkillContractError):
        validate_manifest(broken)


def test_unknown_fields_fail_closed():
    broken = copy.deepcopy(VALID)
    broken["unreviewed_capability"] = True
    with pytest.raises(SkillContractError, match="unknown fields"):
        validate_manifest(broken)


def test_high_risk_requires_approval():
    broken = copy.deepcopy(VALID)
    broken["risk"] = "high"
    with pytest.raises(SkillContractError, match="approval-required"):
        validate_manifest(broken)


def test_bounded_autonomy_rejects_production_write():
    broken = copy.deepcopy(VALID)
    broken["autonomy"] = "bounded_autonomous"
    broken["permissions"]["write"] = ["production"]
    with pytest.raises(SkillContractError, match="bounded_autonomous"):
        validate_manifest(broken)


def test_duplicate_input_names_are_rejected():
    broken = copy.deepcopy(VALID)
    broken["inputs"].append(copy.deepcopy(broken["inputs"][0]))
    with pytest.raises(SkillContractError, match="duplicate inputs"):
        validate_manifest(broken)


def test_workflow_must_be_sequential():
    broken = copy.deepcopy(VALID)
    broken["workflow"][1]["step"] = 3
    with pytest.raises(SkillContractError, match="sequential"):
        validate_manifest(broken)


def test_write_cannot_bypass_approval_declaration():
    broken = copy.deepcopy(VALID)
    broken["permissions"]["write"] = ["send_email"]
    broken["permissions"]["requires_approval"] = ["send_email"]
    with pytest.raises(SkillContractError, match="both unconditional write"):
        validate_manifest(broken)
