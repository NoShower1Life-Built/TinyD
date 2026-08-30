from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "control"


def read(name: str):
    return json.loads((CONTROL / name).read_text(encoding="utf-8"))


class ControlModelTests(unittest.TestCase):
    def test_requirements_have_tests(self):
        requirements = read("requirements.json")["requirements"]
        mappings = {item["id"] for item in read("../tests/mappings.json")["tests"]}
        for requirement in requirements:
            self.assertTrue(requirement.get("tests"), requirement["id"])
            for test_id in requirement["tests"]:
                self.assertIn(test_id, mappings)

    def test_verification_predicates_require_evidence(self):
        predicates = read("control-model.json")["verification"]["requiredPredicates"]
        self.assertIn("evidence_exists", predicates)
        self.assertIn("evidence_valid", predicates)
        self.assertIn("evidence_matches_source", predicates)

    def test_planner_blocks_incomplete_dependencies(self):
        tasks = read("tasks.json")["tasks"]
        by_id = {task["id"]: task for task in tasks}
        for task in tasks:
            if task.get("state") == "COMPLETE":
                for dependency in task.get("dependsOn", []):
                    self.assertEqual(by_id[dependency]["state"], "COMPLETE")

    def test_execution_state_machine_has_no_verification_shortcuts(self):
        state_machine = read("state-machine.json")
        for transition in state_machine["forbiddenShortcuts"]:
            source, destination = transition.split("->")
            self.assertNotIn(destination, state_machine["allowedTransitions"].get(source, []))


if __name__ == "__main__":
    unittest.main()
