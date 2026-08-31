import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from execution import ExecutionLedger, ExecutionRecord, ExecutionState, ExecutionWorker


class ProductionExecutionTests(unittest.TestCase):
    def test_worker_persists_success_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = ExecutionLedger(root / "execution.db")
            worker = ExecutionWorker(ledger, root, timeout_seconds=5, worker_id="worker-a")

            first = worker.execute("TASK-1", [sys.executable, "-c", "print('ok')"], "rev-1")
            second = worker.execute("TASK-1", [sys.executable, "-c", "raise SystemExit(9)"], "rev-1")

            self.assertEqual(first.state, ExecutionState.SUCCEEDED)
            self.assertEqual(second.state, ExecutionState.SUCCEEDED)
            self.assertEqual(len(list(ledger.all())), 1)

    def test_expired_running_lease_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = ExecutionLedger(root / "execution.db")
            execution_id = "exec-recovery"
            self.assertTrue(ledger.acquire_lease(execution_id, "TASK-RECOVER", "rev-1", "dead-worker", 1))
            ledger.put(ExecutionRecord(execution_id, "TASK-RECOVER", "rev-1", ExecutionState.RUNNING, metadata={"workerId": "dead-worker"}))
            time.sleep(1.1)

            recovered = ledger.recover_expired()
            record = ledger.get(execution_id)

            self.assertEqual(recovered, [execution_id])
            self.assertIsNotNone(record)
            self.assertEqual(record.state, ExecutionState.DISPATCHED)
            self.assertIn("lease expired", record.error or "")

    def test_worker_interruption_leaves_durable_running_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "execution.db"
            script = (
                "from pathlib import Path; "
                "import os; "
                "from execution import ExecutionLedger, ExecutionRecord, ExecutionState; "
                "p=Path(r'%s'); l=ExecutionLedger(p); "
                "eid='exec-interrupted'; "
                "assert l.acquire_lease(eid,'TASK-INT','rev-1','crashed-worker',1); "
                "l.put(ExecutionRecord(eid,'TASK-INT','rev-1',ExecutionState.RUNNING,metadata={'workerId':'crashed-worker'})); "
                "os._exit(0)"
            ) % db
            subprocess.run([sys.executable, "-c", script], check=True)

            ledger = ExecutionLedger(db)
            record = ledger.get("exec-interrupted")
            self.assertIsNotNone(record)
            self.assertEqual(record.state, ExecutionState.RUNNING)
            time.sleep(1.1)
            self.assertEqual(ledger.recover_expired(), ["exec-interrupted"])
            self.assertEqual(ledger.get("exec-interrupted").state, ExecutionState.DISPATCHED)


if __name__ == "__main__":
    unittest.main()
