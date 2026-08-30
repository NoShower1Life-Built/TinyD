from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequirementState:
    state: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TaskState:
    state: str
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseState:
    state: str
    reasons: tuple[str, ...]


class CanonicalStateEngine:
    """Derive control state from declared facts; never trusts asserted derived state."""

    def __init__(self, requirements: list[dict[str, Any]], tasks: list[dict[str, Any]],
                 tests: dict[str, dict[str, Any]] | None = None,
                 executions: dict[str, dict[str, Any]] | None = None,
                 evidence: dict[str, dict[str, Any]] | None = None):
        self.requirements = {r["id"]: r for r in requirements}
        self.tasks = {t["id"]: t for t in tasks}
        self.tests = tests or {}
        self.executions = executions or {}
        self.evidence = evidence or {}

    def task_state(self, task_id: str) -> TaskState:
        task = self.tasks[task_id]
        blockers = tuple(
            dependency for dependency in task.get("dependsOn", [])
            if dependency not in self.tasks or self.tasks[dependency].get("state") != "COMPLETE"
        )
        if blockers:
            return TaskState("BLOCKED", blockers, ("dependency_incomplete",))
        declared = task.get("state", "PLANNED")
        if declared == "PLANNED":
            return TaskState("READY", (), ())
        return TaskState(declared, (), ())

    def requirement_state(self, requirement_id: str) -> RequirementState:
        requirement = self.requirements[requirement_id]
        reasons: list[str] = []
        tests = requirement.get("tests", [])
        if not tests:
            reasons.append("required_tests_missing")
        for test_id in tests:
            test = self.tests.get(test_id)
            if not test:
                reasons.append(f"test_missing:{test_id}")
            elif not test.get("passed", False):
                reasons.append(f"test_not_passing:{test_id}")
        if reasons:
            return RequirementState("UNVERIFIED", tuple(reasons))
        return RequirementState("VERIFIED", ())

    def release_state(self) -> ReleaseState:
        reasons: list[str] = []
        for requirement_id, requirement in self.requirements.items():
            if requirement.get("required", True):
                state = self.requirement_state(requirement_id)
                if state.state != "VERIFIED":
                    reasons.extend(f"{requirement_id}:{reason}" for reason in state.reasons)
        for task_id in self.tasks:
            state = self.task_state(task_id)
            if state.state == "BLOCKED":
                reasons.append(f"{task_id}:blocked")
        if reasons:
            return ReleaseState("RELEASE_BLOCKED", tuple(sorted(set(reasons))))
        return ReleaseState("RELEASE_ALLOWED", ())

    def snapshot(self) -> dict[str, Any]:
        requirements = {
            rid: {"state": self.requirement_state(rid).state,
                  "reasons": list(self.requirement_state(rid).reasons)}
            for rid in self.requirements
        }
        tasks = {
            tid: {"state": self.task_state(tid).state,
                  "blockers": list(self.task_state(tid).blockers),
                  "reasons": list(self.task_state(tid).reasons)}
            for tid in self.tasks
        }
        release = self.release_state()
        return {
            "requirements": requirements,
            "tasks": tasks,
            "release": {"state": release.state, "reasons": list(release.reasons)},
        }
