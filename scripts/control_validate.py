#!/usr/bin/env python3
"""Validate core control-model invariants using only the Python standard library."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "control"


def load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    model = load(CONTROL / "control-model.json")
    states = load(CONTROL / "state-machine.json")
    requirements = load(CONTROL / "requirements.json")["requirements"]
    tasks = load(CONTROL / "tasks.json")["tasks"]
    mappings = load(ROOT / "tests" / "mappings.json")["tests"]

    req_ids = {r["id"] for r in requirements}
    mapping_by_id = {item["id"]: item for item in mappings}
    task_ids = {t["id"] for t in tasks}

    for requirement in requirements:
        tests = requirement.get("tests", [])
        if not tests:
            fail(errors, f"requirement {requirement['id']} has no test")
        for test_id in tests:
            mapping = mapping_by_id.get(test_id)
            if mapping is None:
                fail(errors, f"requirement {requirement['id']} references unknown test {test_id}")
                continue
            test_path = ROOT / mapping["path"]
            if not test_path.is_file():
                fail(errors, f"test {test_id} has no executable file: {mapping['path']}")

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

    for transition in states.get("forbiddenShortcuts", []):
        source, destination = transition.split("->", 1)
        if destination in allowed.get(source, []):
            fail(errors, f"forbidden shortcut is allowed: {transition}")

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
    print(f"requirements={len(requirements)} tasks={len(tasks)} tests={len(mappings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
