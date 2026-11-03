"""Deterministic DAG validation and scheduling primitives for TinyD.

The scheduler produces a stable plan only. It does not execute work or grant
capabilities; execution authorization remains in the runtime/worker boundary.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import heapq
from typing import Iterable


class ScheduleError(ValueError):
    """Raised when a workflow graph is invalid or cannot be scheduled."""


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    dependencies: tuple[str, ...] = ()


class DeterministicScheduler:
    """Validate DAGs and produce stable topological execution waves."""

    @staticmethod
    def _index(tasks: Iterable[Task]) -> tuple[dict[str, Task], dict[str, set[str]]]:
        indexed: dict[str, Task] = {}
        for task in tasks:
            if not isinstance(task, Task):
                raise ScheduleError("every task must be a Task instance")
            if not isinstance(task.id, str) or not task.id.strip():
                raise ScheduleError("task id must be a non-empty string")
            if task.id in indexed:
                raise ScheduleError(f"duplicate task id: {task.id}")
            if len(task.dependencies) != len(set(task.dependencies)):
                raise ScheduleError(f"duplicate dependencies for task: {task.id}")
            if any(not isinstance(dep, str) or not dep.strip() for dep in task.dependencies):
                raise ScheduleError(f"dependencies for task {task.id} must be non-empty strings")
            indexed[task.id] = task

        dependents: dict[str, set[str]] = defaultdict(set)
        for task in indexed.values():
            for dependency in task.dependencies:
                if dependency == task.id:
                    raise ScheduleError(f"task cannot depend on itself: {task.id}")
                if dependency not in indexed:
                    raise ScheduleError(
                        f"task {task.id} references unknown dependency: {dependency}"
                    )
                dependents[dependency].add(task.id)
        return indexed, dependents

    def levels(self, tasks: Iterable[Task]) -> list[list[str]]:
        """Return deterministic parallelizable waves; each wave is lexically sorted."""
        indexed, dependents = self._index(tasks)
        remaining = {task_id: len(task.dependencies) for task_id, task in indexed.items()}
        ready = [task_id for task_id, count in remaining.items() if count == 0]
        heapq.heapify(ready)
        levels: list[list[str]] = []
        visited = 0

        while ready:
            current = [heapq.heappop(ready) for _ in range(len(ready))]
            levels.append(current)
            visited += len(current)
            next_ready: list[str] = []
            for task_id in current:
                for dependent in sorted(dependents[task_id]):
                    remaining[dependent] -= 1
                    if remaining[dependent] == 0:
                        next_ready.append(dependent)
            for task_id in next_ready:
                heapq.heappush(ready, task_id)

        if visited != len(indexed):
            cyclic = sorted(task_id for task_id, count in remaining.items() if count > 0)
            raise ScheduleError(f"workflow contains a dependency cycle involving: {', '.join(cyclic)}")
        return levels

    def order(self, tasks: Iterable[Task]) -> list[str]:
        """Return a stable topological order, preserving dependency constraints."""
        return [task_id for level in self.levels(tasks) for task_id in level]
