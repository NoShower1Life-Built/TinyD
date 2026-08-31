from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from execution import ExecutionLedger, ExecutionRecord, ExecutionRunner, ExecutionState


class ControlRuntime:
    """Dispatch only planner-READY tasks and feed terminal results back into runtime state."""

    def __init__(self, root: Path, execution_db: Path) -> None:
        self.root = root.resolve()
        self.ledger = ExecutionLedger(execution_db)
        self.runner = ExecutionRunner(self.root)

    @staticmethod
    def load_tasks(path: Path) -> list[dict]:
        return json.loads(path.read_text(encoding="utf-8"))["tasks"]

    def dispatch(self, task: dict, command: list[str], source_revision: str) -> ExecutionRecord:
        if task.get("state") not in {"READY", "PLANNED"}:
            raise RuntimeError(f"task {task['id']} is not dispatchable: {task.get('state')}")
        record = self.runner.run(task["id"], command, source_revision)
        self.ledger.put(record)
        return record

    def task_state(self, task_id: str, source_revision: str) -> str:
        records = self.ledger.for_task(task_id, source_revision)
        if not records: return "PLANNED"
        latest = records[-1]
        return {ExecutionState.SUCCEEDED: "COMPLETE", ExecutionState.FAILED: "FAILED", ExecutionState.TIMED_OUT: "FAILED", ExecutionState.CANCELLED: "FAILED"}.get(latest.state, latest.state.value)

    def ready_tasks(self, tasks: list[dict], source_revision: str) -> list[dict]:
        states = {t["id"]: self.task_state(t["id"], source_revision) for t in tasks}
        return [t for t in tasks if states[t["id"]] in {"PLANNED", "READY"} and all(states[d] == "COMPLETE" for d in t.get("dependsOn", []))]
