from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from evidence import EvidenceLedger, EvidenceRecord
from execution import ExecutionLedger, ExecutionState, ExecutionWorker


class TaskDispatcher:
    def __init__(self, root: Path, execution_db: Path, evidence_path: Path) -> None:
        self.root = root.resolve()
        self.executions = ExecutionLedger(execution_db)
        self.evidence = EvidenceLedger(evidence_path)
        self.worker = ExecutionWorker(self.executions, self.root)

    def dispatch(self, task: dict, command: list[str], source_revision: str) -> dict:
        task_id = task["id"]
        dependencies = task.get("dependsOn", [])
        if any(not self.executions.for_task(dep, source_revision) or self.executions.for_task(dep, source_revision)[-1].state is not ExecutionState.SUCCEEDED for dep in dependencies):
            raise RuntimeError(f"task {task_id} has incomplete dependencies")
        execution = self.worker.execute(task_id, command, source_revision)
        if execution.state is ExecutionState.SUCCEEDED:
            payload = {"result": "pass", "taskId": task_id, "exitCode": execution.exit_code, "executionId": execution.execution_id}
            evidence_id = self.evidence.evidence_id(task.get("requirements", [task_id])[0], execution.execution_id, source_revision, payload)
            self.evidence.append(EvidenceRecord(evidence_id, task.get("requirements", [task_id])[0], execution.execution_id, source_revision, "execution-result", payload, datetime.now(timezone.utc).isoformat()))
        return execution.as_dict()

    def derived_state(self, task: dict, source_revision: str) -> str:
        records = self.executions.for_task(task["id"], source_revision)
        if records:
            return "COMPLETE" if records[-1].state is ExecutionState.SUCCEEDED else records[-1].state.value
        for dep in task.get("dependsOn", []):
            dependency_records = self.executions.for_task(dep, source_revision)
            if not dependency_records or dependency_records[-1].state is not ExecutionState.SUCCEEDED:
                return "BLOCKED"
        return "READY"
