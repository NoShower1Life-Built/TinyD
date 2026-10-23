"""Fail-closed validation for versioned TinyD skill manifests.

This validates declarations only. It does not execute tools or grant permissions;
runtime authorization remains the responsibility of TinyD.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_AUTONOMY = {"observe", "recommend", "prepare", "approved_execute", "bounded_autonomous"}
_RISK = {"low", "medium", "high", "critical"}


class SkillContractError(ValueError):
    """Raised when a skill manifest violates the contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SkillContractError(message)


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return an isolated copy of a manifest without side effects."""
    _require(isinstance(manifest, Mapping), "manifest must be an object")
    candidate = copy.deepcopy(dict(manifest))
    _require(all(isinstance(key, str) for key in candidate), "manifest field names must be strings")

    required = {
        "contract_version", "id", "version", "name", "purpose", "triggers",
        "inputs", "outputs", "tools", "permissions", "risk", "autonomy",
        "workflow", "failure_policy", "verification",
    }
    missing, unknown = required - set(candidate), set(candidate) - required
    _require(not missing, f"missing required fields: {', '.join(sorted(missing))}")
    _require(not unknown, f"unknown fields: {', '.join(sorted(unknown))}")
    _require(candidate["contract_version"] == "1.0", "contract_version must be '1.0'")
    _require(isinstance(candidate["id"], str) and bool(_ID.fullmatch(candidate["id"])), "id must be 2-63 lowercase letters, digits, or hyphens and start with a letter")
    _require(isinstance(candidate["version"], str) and bool(_SEMVER.fullmatch(candidate["version"])), "version must be valid semantic version MAJOR.MINOR.PATCH with valid prerelease/build metadata")
    for field in ("name", "purpose"):
        _require(isinstance(candidate[field], str) and candidate[field].strip(), f"{field} must be a non-empty string")

    triggers = candidate["triggers"]
    _require(isinstance(triggers, list) and triggers and all(isinstance(x, str) and x.strip() for x in triggers), "triggers must be a non-empty list of non-empty strings")
    _require(len(triggers) == len(set(triggers)), "triggers must not contain duplicates")

    for field in ("inputs", "outputs"):
        value = candidate[field]
        _require(isinstance(value, list) and value, f"{field} must be a non-empty list")
        seen = set()
        for item in value:
            _require(isinstance(item, dict), f"each {field} entry must be an object")
            _require(set(item) == {"name", "type", "required", "description"}, f"each {field} entry must contain exactly name, type, required, description")
            _require(isinstance(item["name"], str) and bool(_ID.fullmatch(item["name"])), f"{field} entry name is invalid")
            _require(item["name"] not in seen, f"duplicate {field} name: {item['name']}")
            seen.add(item["name"])
            _require(isinstance(item["type"], str) and item["type"].strip(), f"{field}.{item['name']}.type must be non-empty")
            _require(isinstance(item["required"], bool), f"{field}.{item['name']}.required must be boolean")
            _require(isinstance(item["description"], str) and item["description"].strip(), f"{field}.{item['name']}.description must be non-empty")

    tools = candidate["tools"]
    _require(isinstance(tools, list) and all(isinstance(x, str) and x.strip() for x in tools), "tools must be a list of non-empty strings")
    _require(len(tools) == len(set(tools)), "tools must not contain duplicates")

    permissions = candidate["permissions"]
    _require(isinstance(permissions, dict) and set(permissions) == {"read", "write", "requires_approval"}, "permissions must contain exactly read, write, requires_approval")
    for key in ("read", "write", "requires_approval"):
        _require(isinstance(permissions[key], list) and all(isinstance(x, str) and x.strip() for x in permissions[key]), f"permissions.{key} must be a list of non-empty strings")
        _require(len(permissions[key]) == len(set(permissions[key])), f"permissions.{key} must not contain duplicates")
    write_permissions = set(permissions["write"])
    approval_permissions = set(permissions["requires_approval"])
    _require(approval_permissions <= write_permissions, "requires_approval must be a subset of declared write permissions")

    risk, autonomy = candidate["risk"], candidate["autonomy"]
    _require(isinstance(risk, str) and risk in _RISK, f"risk must be one of {sorted(_RISK)}")
    _require(isinstance(autonomy, str) and autonomy in _AUTONOMY, f"autonomy must be one of {sorted(_AUTONOMY)}")
    if autonomy == "bounded_autonomous":
        _require(risk == "low", "bounded_autonomous is permitted only for low-risk skills")
        _require(not approval_permissions, "bounded_autonomous skills cannot declare approval-required actions")
        _require(not write_permissions & {"financial", "destructive", "production"}, "bounded_autonomous skills cannot perform financial, destructive, or production writes")
    if risk in {"high", "critical"}:
        _require(bool(write_permissions), "high/critical risk skills must declare write permissions")
        _require(write_permissions <= approval_permissions, "every high/critical risk write permission must require approval")

    workflow = candidate["workflow"]
    _require(isinstance(workflow, list) and workflow and all(
        isinstance(x, dict) and set(x) == {"step", "action", "success_condition"}
        and isinstance(x["step"], int) and not isinstance(x["step"], bool) and x["step"] > 0
        and isinstance(x["action"], str) and x["action"].strip()
        and isinstance(x["success_condition"], str) and x["success_condition"].strip()
        for x in workflow
    ), "workflow must be a non-empty list of valid numbered steps")
    steps = [x["step"] for x in workflow]
    _require(steps == list(range(1, len(steps) + 1)), "workflow steps must be sequential starting at 1")

    failure = candidate["failure_policy"]
    _require(isinstance(failure, dict) and set(failure) == {"retryable_errors", "max_attempts", "on_exhaustion", "idempotency_key", "compensation_action"}, "failure_policy has invalid shape")
    _require(isinstance(failure["retryable_errors"], list) and all(isinstance(x, str) and x.strip() for x in failure["retryable_errors"]), "failure_policy.retryable_errors must be a list of strings")
    _require(len(failure["retryable_errors"]) == len(set(failure["retryable_errors"])), "failure_policy.retryable_errors must not contain duplicates")
    _require(isinstance(failure["max_attempts"], int) and not isinstance(failure["max_attempts"], bool) and 1 <= failure["max_attempts"] <= 10, "failure_policy.max_attempts must be an integer from 1 to 10")
    _require(isinstance(failure["on_exhaustion"], str) and failure["on_exhaustion"] in {"stop", "escalate", "compensate"}, "failure_policy.on_exhaustion must be stop, escalate, or compensate")
    _require(isinstance(failure["idempotency_key"], str) and failure["idempotency_key"].strip(), "failure_policy.idempotency_key must be non-empty")
    compensation = failure["compensation_action"]
    _require(compensation is None or (isinstance(compensation, str) and compensation.strip()), "failure_policy.compensation_action must be null or a non-empty action identifier")
    _require((failure["on_exhaustion"] == "compensate") == (compensation is not None), "compensation_action must be declared if and only if on_exhaustion is compensate")

    verification = candidate["verification"]
    _require(isinstance(verification, dict) and set(verification) == {"acceptance_criteria", "evidence_required", "independent_check"}, "verification has invalid shape")
    _require(isinstance(verification["acceptance_criteria"], list) and verification["acceptance_criteria"] and all(isinstance(x, str) and x.strip() for x in verification["acceptance_criteria"]), "verification.acceptance_criteria must be a non-empty list of strings")
    _require(isinstance(verification["evidence_required"], list) and all(isinstance(x, str) and x.strip() for x in verification["evidence_required"]), "verification.evidence_required must be a list of strings")
    _require(isinstance(verification["independent_check"], bool), "verification.independent_check must be boolean")
    return candidate
