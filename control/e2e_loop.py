from __future__ import annotations

import tempfile
from pathlib import Path

from execution import ExecutionLedger, ExecutionRunner, ExecutionState
from evidence import EvidenceLedger, EvidenceRecord, VerificationEngine


def run_loop(root: Path, requirement_id: str = "REQ-CONTROL-001", task_id: str = "TASK-CONTROL-001", revision: str = "test-revision") -> dict:
    execution_db = root / "execution.db"
    evidence_file = root / "evidence.jsonl"
    executions = ExecutionLedger(execution_db)
    runner = ExecutionRunner(root, timeout_seconds=10)
    execution = runner.run(task_id, ["python3", "-c", "print('CONTROL_PASS')"], revision)
    executions.put(execution)
    if execution.state is not ExecutionState.SUCCEEDED:
        raise AssertionError("control execution did not succeed")
    ledger = EvidenceLedger(evidence_file)
    payload = {"result": "pass", "taskId": task_id}
    evidence_id = ledger.evidence_id(requirement_id, execution.execution_id, revision, payload)
    ledger.append(EvidenceRecord(evidence_id, requirement_id, execution.execution_id, revision, "test-result", payload, "2026-08-30T00:00:00+00:00"))
    verification = VerificationEngine(executions).verify(requirement_id, ledger.records(), revision, [{"op": "equals", "field": "result", "value": "pass"}])
    return {"execution": execution.as_dict(), "evidence": [e.as_dict() for e in ledger.records()], "verification": verification.claim.as_dict(), "verificationState": verification.state}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        result = run_loop(Path(tmp))
        assert result["verificationState"] == "VERIFIED"
        print("CONTROL LOOP: PASS")
