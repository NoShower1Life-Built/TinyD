#!/usr/bin/env python3
"""Generate an ordered queue from control/tasks.json using dependency state."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tasks():
    return json.loads((ROOT / "control" / "tasks.json").read_text(encoding="utf-8"))["tasks"]


def plan(tasks):
    by_id = {task["id"]: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("duplicate task id")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"dependency cycle detected at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        task = by_id[task_id]
        for dep in task.get("dependsOn", []):
            if dep not in by_id:
                raise ValueError(f"missing dependency {dep} for {task_id}")
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in tasks:
        visit(task["id"])

    ordered = []
    for task_id in sorted(visited, key=lambda value: (by_id[value].get("priority", 999), value)):
        task = by_id[task_id]
        blockers = [dep for dep in task.get("dependsOn", []) if by_id[dep].get("state") != "COMPLETE"]
        state = "READY" if not blockers and task.get("state") in {"PLANNED", "READY"} else task.get("state", "PLANNED")
        if blockers:
            state = "BLOCKED"
        ordered.append({
            "taskId": task_id,
            "priority": task.get("priority", 999),
            "state": state,
            "dependsOn": task.get("dependsOn", []),
            "blockingReasons": ["dependency_incomplete"] if blockers else [],
            "blockers": blockers,
            "requirements": task.get("requirements", []),
            "title": task.get("title", "")
        })
    return ordered


def main() -> int:
    try:
        queue = plan(load_tasks())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"PLANNER: FAIL: {exc}")
        return 1
    print(json.dumps({"queue": queue}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
