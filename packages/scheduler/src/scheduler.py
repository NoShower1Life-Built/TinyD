from __future__ import annotations

from dataclasses import dataclass
import heapq


@dataclass(frozen=True)
class Task:
    id: str
    dependencies: tuple[str, ...] = ()


class DeterministicScheduler:
    """Stable Kahn topological sort; independent tasks are ordered by task ID."""

    def order(self, tasks: list[Task]) -> list[str]:
        by_id = {task.id: task for task in tasks}
        if len(by_id) != len(tasks):
            raise ValueError("duplicate task id")
        indegree = {task.id: 0 for task in tasks}
        dependents: dict[str, list[str]] = {task.id: [] for task in tasks}
        for task in tasks:
            for dependency in task.dependencies:
                if dependency not in by_id:
                    raise ValueError(f"unknown dependency: {dependency}")
                indegree[task.id] += 1
                dependents[dependency].append(task.id)
        for values in dependents.values():
            values.sort()
        ready = [task_id for task_id, degree in indegree.items() if degree == 0]
        heapq.heapify(ready)
        result: list[str] = []
        while ready:
            task_id = heapq.heappop(ready)
            result.append(task_id)
            for dependent in dependents[task_id]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(ready, dependent)
        if len(result) != len(tasks):
            raise ValueError("workflow contains a dependency cycle")
        return result
