import tempfile
import unittest
from pathlib import Path

from control.dispatcher import TaskDispatcher
from control.replan import replan


class DownstreamProgressionTests(unittest.TestCase):
    def test_each_successful_execution_unblocks_next_task(self):
        tasks = [
            {"id": "TASK-CONTROL-001", "dependsOn": [], "requirements": ["REQ-CONTROL-001"]},
            {"id": "TASK-CONTROL-002", "dependsOn": ["TASK-CONTROL-001"], "requirements": ["REQ-CONTROL-001"]},
            {"id": "TASK-CONTROL-003", "dependsOn": ["TASK-CONTROL-002"], "requirements": ["REQ-CONTROL-002"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispatcher = TaskDispatcher(root, root / "execution.db", root / "evidence.jsonl")
            revision = "progression-revision"

            queue = replan(tasks, dispatcher, revision)
            self.assertEqual(queue[0]["taskId"], "TASK-CONTROL-001")
            self.assertEqual(queue[0]["state"], "READY")

            dispatcher.dispatch(tasks[0], ["python3", "-c", "print('task-001')"], revision)
            queue = replan(tasks, dispatcher, revision)
            self.assertEqual(queue[1]["taskId"], "TASK-CONTROL-002")
            self.assertEqual(queue[1]["state"], "READY")

            dispatcher.dispatch(tasks[1], ["python3", "-c", "print('task-002')"], revision)
            queue = replan(tasks, dispatcher, revision)
            self.assertEqual(queue[2]["taskId"], "TASK-CONTROL-003")
            self.assertEqual(queue[2]["state"], "READY")

            dispatcher.dispatch(tasks[2], ["python3", "-c", "print('task-003')"], revision)
            self.assertEqual(dispatcher.derived_state(tasks[2], revision), "COMPLETE")
            self.assertEqual(len(list(dispatcher.executions.all())), 3)
            self.assertEqual(len(dispatcher.evidence.records()), 3)


if __name__ == "__main__":
    unittest.main()
