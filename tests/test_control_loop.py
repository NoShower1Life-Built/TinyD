import tempfile
import unittest
from pathlib import Path

from control.e2e_loop import run_loop


class ControlLoopTests(unittest.TestCase):
    def test_complete_loop_reaches_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_loop(Path(tmp))
            self.assertEqual(result["execution"]["state"], "SUCCEEDED")
            self.assertEqual(len(result["evidence"]), 1)
            self.assertTrue(result["verification"]["verified"])
            self.assertEqual(result["verificationState"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
