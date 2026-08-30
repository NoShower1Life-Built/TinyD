#!/usr/bin/env python3
"""Validate core control-model invariants using only the Python standard library."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "control"


def load(name: str):
    with (CONTROL / name).open(encoding="utf-8") as f:
        return json.load(f)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    model = load("control-model.json")
    states = load("state-machine.json")
    requirements = load("requirements.json")["requirements"]
    tasks = load("tasks.json")["tasks"]

    req_ids = {r["id"] for r in requirements}
    test_ids = {
        test_id
        for requirement in requirements
        for test_id in requirement.get("tests", [])
    }
    task_ids = {t["id"] for t in tasks}

    for requirement in requirements:
        if not requirement.get("tests"):
            fail(errors, f"requirement {requirement['id']} has no test")
        for test_id in requirement.get("tests", []):
            if test_id not in test_ids:
                fail(errors, f"requirement {requirement['id']} references unknown test {test_id}")

    for task in tasks:
        for dependency in task.get("dependsOn", []):
            if dependency not in task_ids:
                fail(errors, f"task {task['id']} references missing dependency {dependency}")
        for requirement_id in task.get("requirements", []):
            if requirement_id not in req_ids:
                fail(errors, f"task {task['id']} references unknown requirement {requirement_id}")
        if task.get("state") == "COMPLETE":
            for dependency in task.get("dependsOn", []):
                dependency_record = next(t for t in tasks if t["id"] == dependency)
                if dependency_record.get("state") != "COMPLETE":
                    fail(errors, f"task {task['id']} is complete while dependency {dependency} is incomplete")

    allowed = states["allowedTransitions"]
    for source, destinations in allowed.items():
        if source not in states["executionStates"]:
            fail(errors, f"state {source} is not declared")
        for destination in destinations:
            if destination not in states["executionStates"]:
                fail(errors, f"transition {source}->{destination} uses undeclared state {destination}")

    if not model.get("verification", {}).get("requiredPredicates"):
        fail(errors, "verification predicate set is empty")
    if not model.get("readiness", {}).get("requiredPredicates"):
        fail(errors, "readiness predicate set is empty")

    if errors:
        print("CONTROL VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CONTROL VALIDATION: PASS")
    print(f"requirements={len(requirements)} tasks={len(tasks)} tests={len(test_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
