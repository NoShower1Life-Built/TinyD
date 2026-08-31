from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ExecutionState(StrEnum):
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    task_id: str
    source_revision: str
    state: ExecutionState
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "taskId": self.task_id,
            "sourceRevision": self.source_revision,
            "state": self.state.value,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "exitCode": self.exit_code,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata or {},
        }
