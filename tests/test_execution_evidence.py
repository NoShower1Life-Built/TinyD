import tempfile
import unittest
from pathlib import Path

from execution import ExecutionRunner, ExecutionState
from evidence import EvidenceLedger, EvidenceRecord, VerificationEngine


class ExecutionEvidenceTests(unittest.TestCase):
    def test_runner_records_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = ExecutionRunner(Path(tmp)).run("TASK-1", ["python3", "-c", "print('ok')"], "rev-1")
            self.assertEqual(record.state, ExecutionState.SUCCEEDED)
            self.assertEqual(record.exit_code, 0)
            self.assertTrue(record.execution_id.startswith("exec-"))

    def test_runner_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = ExecutionRunner(Path(tmp)).run("TASK-1", ["python3", "-c", "raise SystemExit(3)"], "rev-1")
            self.assertEqual(record.state, ExecutionState.FAILED)
            self.assertEqual(record.exit_code, 3)

    def test_verification_requires_current_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            payload = {"result": "pass"}
            evidence_id = ledger.evidence_id("REQ-1", "exec-1", "rev-1", payload)
            ledger.append(EvidenceRecord(evidence_id, "REQ-1", "exec-1", "rev-1", "test-result", payload, "2026-08-30T00:00:00+00:00"))
            engine = VerificationEngine()
            self.assertEqual(engine.verify("REQ-1", ledger.records(), "rev-1").state, "VERIFIED")
            self.assertEqual(engine.verify("REQ-1", ledger.records(), "rev-2").state, "STALE")

    def test_verification_without_evidence_fails(self):
        result = VerificationEngine().verify("REQ-1", [], "rev-1")
        self.assertFalse(result.claim.verified)
        self.assertEqual(result.state, "INVALID")


if __name__ == "__main__":
    unittest.main()
