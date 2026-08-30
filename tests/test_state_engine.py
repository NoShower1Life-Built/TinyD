import unittest

from control.state_engine import CanonicalStateEngine


class CanonicalStateEngineTests(unittest.TestCase):
    def test_incomplete_dependency_blocks_task(self):
        engine = CanonicalStateEngine(
            requirements=[],
            tasks=[
                {"id": "A", "state": "PLANNED", "dependsOn": ["B"]},
                {"id": "B", "state": "PLANNED", "dependsOn": []},
            ],
        )
        state = engine.task_state("A")
        self.assertEqual(state.state, "BLOCKED")
        self.assertEqual(state.blockers, ("B",))

    def test_requirement_without_test_is_unverified(self):
        engine = CanonicalStateEngine(
            requirements=[{"id": "R", "required": True, "tests": []}],
            tasks=[],
        )
        state = engine.requirement_state("R")
        self.assertEqual(state.state, "UNVERIFIED")
        self.assertIn("required_tests_missing", state.reasons)

    def test_passing_test_can_verify_requirement(self):
        engine = CanonicalStateEngine(
            requirements=[{"id": "R", "required": True, "tests": ["T"]}],
            tasks=[],
            tests={"T": {"passed": True}},
        )
        self.assertEqual(engine.requirement_state("R").state, "VERIFIED")

    def test_release_is_blocked_by_unverified_requirement(self):
        engine = CanonicalStateEngine(
            requirements=[{"id": "R", "required": True, "tests": []}],
            tasks=[],
        )
        release = engine.release_state()
        self.assertEqual(release.state, "RELEASE_BLOCKED")


if __name__ == "__main__":
    unittest.main()
