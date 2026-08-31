from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import hashlib
import json

from contracts import PolicyDecision


def digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Policy:
    policy_id: str
    version: str
    rules: Mapping[str, Any]

    @property
    def policy_digest(self) -> str:
        return digest({"policy_id": self.policy_id, "version": self.version, "rules": self.rules})


class ImmutablePolicyEngine:
    def __init__(self, policies: Mapping[tuple[str, str], Policy]):
        self._policies = dict(policies)

    def evaluate(self, request: Mapping[str, Any], policy_version: str) -> PolicyDecision:
        policy_id = str(request["policy_id"])
        policy = self._policies.get((policy_id, policy_version))
        if policy is None:
            return PolicyDecision("DENY", policy_id, policy_version, "", digest(request), "policy version unavailable")
        allowed = bool(policy.rules.get("allow", False))
        decision = "ALLOW" if allowed else "DENY"
        return PolicyDecision(decision, policy.policy_id, policy.version, policy.policy_digest,
                              digest(request), "static policy evaluation")
