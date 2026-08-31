from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .ledger import ExecutionLedger
from .runner import ExecutionRunner
from .types import ExecutionRecord, ExecutionState


class ExecutionWorker:
    """Durable worker boundary: claim a lease, execute, and persist the result."""

    def __init__(self, ledger: ExecutionLedger, root: Path, timeout_seconds: float = 300.0, worker_id: str | None = None) -> None:
        self.ledger = ledger
        self.runner = ExecutionRunner(root, timeout_seconds)
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        self.lease_seconds = max(1, int(timeout_seconds) + 30)

    def execute(self, task_id: str, command: Sequence[str], source_revision: str) -> ExecutionRecord:
        execution_id = self.runner._execution_id(task_id, source_revision)
        existing = self.ledger.get(execution_id)
        if existing is not None and existing.state is ExecutionState.SUCCEEDED:
            return existing
        if not self.ledger.acquire_lease(execution_id, task_id, source_revision, self.worker_id, self.lease_seconds):
            existing = self.ledger.get(execution_id)
            if existing is not None:
                return existing
            raise RuntimeError(f"execution {execution_id} could not acquire lease")

        running = ExecutionRecord(
            execution_id, task_id, source_revision, ExecutionState.RUNNING,
            started_at=self._now(), metadata={"workerId": self.worker_id},
        )
        self.ledger.put(running)
        try:
            result = self.runner.run(task_id, command, source_revision)
            metadata = dict(result.metadata or {})
            metadata["workerId"] = self.worker_id
            result = ExecutionRecord(
                result.execution_id, result.task_id, result.source_revision, result.state,
                result.started_at, result.finished_at, result.exit_code, result.output,
                result.error, metadata,
            )
            self.ledger.put(result)
            self.ledger.release_lease(execution_id, self.worker_id)
            return result
        except BaseException:
            raise

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
