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
    "failure_policy": {"retryable_errors": ["rate_limit", "transient_network"], "max_attempts": 3, "on_exhaustion": "escalate", "idempotency_key": "repository+ref+audit_version", "compensation_action": None},
    "verification": {"acceptance_criteria": ["Every finding includes evidence or is explicitly marked as an inference."], "evidence_required": ["repository_ref", "inspected_paths"], "independent_check": True}
}


def test_valid_manifest_returns_deep_copy():
    result = validate_manifest(VALID)
    assert result == VALID and result is not VALID
    assert result["inputs"] is not VALID["inputs"]
    result["inputs"][0]["name"] = "mutated"
    assert VALID["inputs"][0]["name"] == "repository"


@pytest.mark.parametrize("field", ["contract_version", "id", "version", "name", "purpose"])
def test_required_identity_fields_are_enforced(field):
    broken = copy.deepcopy(VALID)
    broken[field] = ""
    with pytest.raises(SkillContractError):
        validate_manifest(broken)


def test_semver_prerelease_and_build_metadata_are_accepted():
    candidate = copy.deepcopy(VALID)
    candidate["version"] = "1.2.3-rc.1+build.7"
    assert validate_manifest(candidate)["version"] == "1.2.3-rc.1+build.7"


@pytest.mark.parametrize("version", ["1.0.0-01", "1.0.0-alpha..1", "01.0.0", "1.0"])
def test_invalid_semver_is_rejected(version):
    candidate = copy.deepcopy(VALID)
    candidate["version"] = version
    with pytest.raises(SkillContractError, match="semantic version"):
        validate_manifest(candidate)


def test_non_string_top_level_keys_fail_cleanly():
    broken = copy.deepcopy(VALID)
    broken[7] = "unexpected"
    with pytest.raises(SkillContractError, match="field names must be strings"):
        validate_manifest(broken)


def test_unknown_fields_fail_closed():
    broken = copy.deepcopy(VALID)
    broken["unreviewed_capability"] = True
    with pytest.raises(SkillContractError, match="unknown fields"):
        validate_manifest(broken)


def test_high_risk_requires_all_writes_to_require_approval():
    broken = copy.deepcopy(VALID)
    broken["risk"] = "high"
    broken["permissions"]["write"] = ["send_email", "production"]
    broken["permissions"]["requires_approval"] = ["send_email"]
    with pytest.raises(SkillContractError, match="every high/critical risk write"):
        validate_manifest(broken)


def test_approval_permissions_must_be_declared_writes():
    broken = copy.deepcopy(VALID)
    broken["permissions"]["requires_approval"] = ["send_email"]
    with pytest.raises(SkillContractError, match="subset of declared write"):
        validate_manifest(broken)


def test_write_permission_can_be_explicitly_approval_gated():
    candidate = copy.deepcopy(VALID)
    candidate["permissions"]["write"] = ["send_email"]
    candidate["permissions"]["requires_approval"] = ["send_email"]
    assert validate_manifest(candidate)["permissions"]["requires_approval"] == ["send_email"]


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


def test_retryable_errors_cannot_be_duplicated():
    broken = copy.deepcopy(VALID)
    broken["failure_policy"]["retryable_errors"].append("rate_limit")
    with pytest.raises(SkillContractError, match="must not contain duplicates"):
        validate_manifest(broken)


def test_boolean_is_not_a_valid_attempt_count():
    broken = copy.deepcopy(VALID)
    broken["failure_policy"]["max_attempts"] = True
    with pytest.raises(SkillContractError, match="integer from 1 to 10"):
        validate_manifest(broken)


def test_compensation_mode_requires_a_declared_action():
    broken = copy.deepcopy(VALID)
    broken["failure_policy"]["on_exhaustion"] = "compensate"
    with pytest.raises(SkillContractError, match="compensation_action"):
        validate_manifest(broken)


def test_compensation_action_is_rejected_for_other_exhaustion_modes():
    broken = copy.deepcopy(VALID)
    broken["failure_policy"]["compensation_action"] = "restore_previous_state"
    with pytest.raises(SkillContractError, match="if and only if"):
        validate_manifest(broken)


def test_compensation_action_must_be_explicit():
    candidate = copy.deepcopy(VALID)
    candidate["failure_policy"]["on_exhaustion"] = "compensate"
    candidate["failure_policy"]["compensation_action"] = "restore_previous_state"
    assert validate_manifest(candidate)["failure_policy"]["compensation_action"] == "restore_previous_state"
