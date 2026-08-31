#!/usr/bin/env python3
"""Generate a deterministic, repository-derived control-loop scoreboard."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "control"


def load(name: str):
    return json.loads((CONTROL / name).read_text(encoding="utf-8"))


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def batch_state(batch: dict) -> dict:
    paths = batch.get("requiredPaths", [])
    present = [p for p in paths if exists(p)]
    missing = [p for p in paths if not exists(p)]
    mode = batch.get("closeWhen")
    if mode == "all_exist":
        state = "CLOSED" if not missing else "OPEN"
    elif batch["id"] == "002":
        state = "PARTIAL" if present else "OPEN"
    else:
        state = "CLOSED" if not missing else "OPEN"
    return {"id": batch["id"], "title": batch["title"], "state": state,
            "present": present, "missing": missing}


def source_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    try:
        model = load("scoreboard-model.json")
        requirements = load("requirements.json")["requirements"]
        tasks = load("tasks.json")["tasks"]
        mappings = json.loads((ROOT / "tests" / "mappings.json").read_text(encoding="utf-8"))["tests"]
        planner = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "scripts" / "plan.py")], cwd=ROOT, text=True))["queue"]
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, KeyError) as exc:
        print(f"SCOREBOARD: FAIL: {exc}")
        return 1

    required_tests = sum(len(r.get("tests", [])) for r in requirements)
    existing_tests = sum(1 for m in mappings if exists(m["path"]))
    execution_infrastructure = exists("execution")
    evidence_infrastructure = exists("evidence")

    controls = {
        "requirement_exists": bool(requirements),
        "implementation_complete": False,
        "dependencies_satisfied": not any(item["state"] == "BLOCKED" for item in planner),
        "required_tests_exist": required_tests == existing_tests,
        "required_tests_pass": False,
        "execution_exists": execution_infrastructure,
        "evidence_exists": evidence_infrastructure,
        "evidence_valid": False,
        "evidence_matches_source": False,
        "no_blocking_findings": False,
    }

    truth = {
        "DEFINED": bool(requirements and tasks),
        "IMPLEMENTED": controls["implementation_complete"],
        "TESTED": controls["required_tests_exist"],
        "EXECUTED": controls["execution_exists"],
        "EVIDENCED": controls["evidence_exists"],
        "VERIFIED": all(controls.values()),
        "CURRENT": False,
        "RELEASEABLE": False,
    }

    findings = []
    if not controls["execution_exists"]:
        findings.append({"severity": "CRITICAL", "id": "execution_missing", "message": "No authoritative execution infrastructure exists."})
    if not controls["evidence_exists"]:
        findings.append({"severity": "CRITICAL", "id": "evidence_missing", "message": "No authoritative evidence ledger exists."})
    if not controls["evidence_matches_source"]:
        findings.append({"severity": "HIGH", "id": "source_binding_missing", "message": "Evidence is not proven to match the current source revision."})
    if not controls["no_blocking_findings"]:
        findings.append({"severity": "HIGH", "id": "blocking_findings", "message": "Blocking findings remain unresolved."})

    release_reasons = [f["message"] for f in findings]
    data = {
        "schemaVersion": model["version"],
        "generatedFrom": "repository",
        "sourceRevision": source_revision(),
        "status": "RELEASE_BLOCKED" if release_reasons else "RELEASE_ALLOWED",
        "truth": truth,
        "controls": controls,
        "counts": {
            "requirements": len(requirements),
            "tasks": len(tasks),
            "tests": len(mappings),
            "requiredTests": required_tests,
            "existingTests": existing_tests,
            "executions": 0,
            "validEvidence": 0,
            "verifiedRequirements": 0,
        },
        "batches": [batch_state(b) for b in model["batches"]],
        "findings": findings,
        "workQueue": planner,
        "releaseReasons": release_reasons,
    }
    print(json.dumps(data, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
