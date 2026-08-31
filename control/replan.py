from __future__ import annotations

from pathlib import Path

from .dispatcher import TaskDispatcher
from scripts.plan import plan


def replan(tasks: list[dict], dispatcher: TaskDispatcher, source_revision: str) -> list[dict]:
    """Replace declared runtime states with derived execution states before planning."""
    runtime_tasks = []
    for task in tasks:
        derived = dispatcher.derived_state(task, source_revision)
        runtime_tasks.append({**task, "state": "COMPLETE" if derived == "COMPLETE" else ("READY" if derived == "READY" else derived)})
    return plan(runtime_tasks)
