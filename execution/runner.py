from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .types import ExecutionRecord, ExecutionState


class ExecutionRunner:
    """Execute an approved task command and return an immutable result record."""

    def __init__(self, root: Path, timeout_seconds: float = 300.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.root = root.resolve()
        self.timeout_seconds = timeout_seconds

    def _execution_id(self, task_id: str, source_revision: str) -> str:
        value = f"{task_id}:{source_revision}".encode()
        return "exec-" + hashlib.sha256(value).hexdigest()[:24]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def run(self, task_id: str, command: Sequence[str], source_revision: str) -> ExecutionRecord:
        if not task_id or not source_revision:
            raise ValueError("task_id and source_revision are required")
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must be a non-empty sequence of strings")

        execution_id = self._execution_id(task_id, source_revision)
        started_at = self._now()
        env = os.environ.copy()
        env["TINYD_EXECUTION_ID"] = execution_id
        env["TINYD_TASK_ID"] = task_id
        env["TINYD_SOURCE_REVISION"] = source_revision
        try:
            completed = subprocess.run(
                list(command), cwd=self.root, env=env, capture_output=True,
                text=True, timeout=self.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionRecord(
                execution_id, task_id, source_revision, ExecutionState.TIMED_OUT,
                started_at, self._now(), None, exc.stdout or "", str(exc),
            )
        except OSError as exc:
            return ExecutionRecord(
                execution_id, task_id, source_revision, ExecutionState.FAILED,
                started_at, self._now(), None, "", str(exc),
            )

        state = ExecutionState.SUCCEEDED if completed.returncode == 0 else ExecutionState.FAILED
        return ExecutionRecord(
            execution_id, task_id, source_revision, state, started_at, self._now(),
            completed.returncode, completed.stdout, completed.stderr or None,
        )
