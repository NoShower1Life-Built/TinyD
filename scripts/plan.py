#!/usr/bin/env python3
"""Generate a deterministic dependency-aware execution queue."""
from __future__ import annotations

import heapq
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

    indegree = {task_id: 0 for task_id in by_id}
    dependents: dict[str, list[str]] = {task_id: [] for task_id in by_id}
    for task in tasks:
        for dependency in task.get("dependsOn", []):
            if dependency not in by_id:
                raise ValueError(f"missing dependency {dependency} for {task['id']}")
            indegree[task["id"]] += 1
            dependents[dependency].append(task["id"])

    heap = []
    for task_id, degree in indegree.items():
        if degree == 0:
            task = by_id[task_id]
            heapq.heappush(heap, (task.get("priority", 999), task_id))

    ordered_ids = []
    while heap:
        _, task_id = heapq.heappop(heap)
        ordered_ids.append(task_id)
        for dependent in sorted(dependents[task_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                task = by_id[dependent]
                heapq.heappush(heap, (task.get("priority", 999), dependent))

    if len(ordered_ids) != len(tasks):
        cycle_nodes = sorted(task_id for task_id, degree in indegree.items() if degree > 0)
        raise ValueError(f"dependency cycle detected: {', '.join(cycle_nodes)}")

    queue = []
    for position, task_id in enumerate(ordered_ids, start=1):
        task = by_id[task_id]
        blockers = [
            dependency
            for dependency in task.get("dependsOn", [])
            if by_id[dependency].get("state") != "COMPLETE"
        ]
        declared_state = task.get("state", "PLANNED")
        state = "BLOCKED" if blockers else ("READY" if declared_state in {"PLANNED", "READY"} else declared_state)
        queue.append({
            "position": position,
            "taskId": task_id,
            "priority": task.get("priority", 999),
            "state": state,
            "dependsOn": task.get("dependsOn", []),
            "blockingReasons": ["dependency_incomplete"] if blockers else [],
            "blockers": blockers,
            "requirements": task.get("requirements", []),
            "title": task.get("title", "")
        })
    return queue


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
