import tempfile
import unittest
from pathlib import Path

from control.dispatcher import TaskDispatcher
from control.replan import replan


class DispatchReplanTests(unittest.TestCase):
    def test_dispatch_creates_execution_and_evidence_then_unblocks_dependent(self):
        tasks = [
            {"id": "A", "dependsOn": [], "requirements": ["R"]},
            {"id": "B", "dependsOn": ["A"], "requirements": ["R"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispatcher = TaskDispatcher(root, root / "execution.db", root / "evidence.jsonl")
            dispatcher.dispatch(tasks[0], ["python3", "-c", "print('ok')"], "rev-1")
            queue = replan(tasks, dispatcher, "rev-1")
            self.assertEqual(queue[0]["state"], "COMPLETE")
            self.assertEqual(queue[1]["state"], "READY")
            self.assertEqual(len(dispatcher.evidence.records()), 1)


if __name__ == "__main__":
    unittest.main()
