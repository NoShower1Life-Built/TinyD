#!/usr/bin/env python3
"""Generate a repository-derived control-loop scoreboard."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; CONTROL=ROOT/"control"
def load(name): return json.loads((CONTROL/name).read_text(encoding="utf-8"))
def exists(path): return (ROOT/path).exists()
def source_revision():
    if os.getenv("TINYD_SOURCE_REVISION"): return os.environ["TINYD_SOURCE_REVISION"]
    try: return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError): return "UNKNOWN"
def main():
    try:
        model=load("scoreboard-model.json"); requirements=load("requirements.json")["requirements"]; tasks=load("tasks.json")["tasks"]
        mappings=json.loads((ROOT/"tests"/"mappings.json").read_text(encoding="utf-8"))["tests"]
        queue=json.loads(subprocess.check_output([sys.executable,str(ROOT/"scripts"/"plan.py")],cwd=ROOT,text=True))["queue"]
        validation=subprocess.run([sys.executable,str(ROOT/"scripts"/"control_validate.py")],cwd=ROOT,text=True,capture_output=True)
    except (OSError,json.JSONDecodeError,subprocess.CalledProcessError,KeyError) as exc:
        print(f"SCOREBOARD: FAIL: {exc}"); return 1
    required_test_ids={tid for r in requirements for tid in r.get("tests",[])}; mapping_by_id={m["id"]:m for m in mappings}
    required_tests_exist=bool(required_test_ids) and all(tid in mapping_by_id and exists(mapping_by_id[tid]["path"]) for tid in required_test_ids)
    implementation_complete=all(all(exists(p) for p in r.get("implementation",[])) for r in requirements if r.get("required"))
    dependencies_satisfied=not any(x["state"]=="BLOCKED" for x in queue)
    execution_exists=exists("execution"); evidence_exists=exists("evidence")
    controls={"requirement_exists":bool(requirements),"implementation_complete":implementation_complete,"dependencies_satisfied":dependencies_satisfied,"required_tests_exist":required_tests_exist,"required_tests_pass":False,"execution_exists":execution_exists,"evidence_exists":evidence_exists,"evidence_valid":False,"evidence_matches_source":False,"no_blocking_findings":False}
    findings=[]
    if validation.returncode!=0: findings.append({"severity":"CRITICAL","id":"control_validation_failed","message":validation.stdout.strip() or validation.stderr.strip()})
    if not dependencies_satisfied: findings.append({"severity":"HIGH","id":"dependencies_incomplete","message":"The ordered work queue contains blocked tasks."})
    if not execution_exists: findings.append({"severity":"CRITICAL","id":"execution_missing","message":"No authoritative execution infrastructure exists."})
    if not evidence_exists: findings.append({"severity":"CRITICAL","id":"evidence_missing","message":"No authoritative evidence ledger exists."})
    if not controls["evidence_matches_source"]: findings.append({"severity":"HIGH","id":"source_binding_missing","message":"No evidence is currently proven against the generated source revision."})
    truth={"DEFINED":bool(requirements and tasks),"IMPLEMENTED":implementation_complete,"TESTED":required_tests_exist and validation.returncode==0,"EXECUTED":False,"EVIDENCED":False,"VERIFIED":False,"CURRENT":False,"RELEASEABLE":False}
    batches=[]
    for b in model["batches"]:
        present=[p for p in b.get("requiredPaths",[]) if exists(p)]; missing=[p for p in b.get("requiredPaths",[]) if not exists(p)]
        if b.get("closeWhen")=="control_validation_passes": state="CLOSED" if validation.returncode==0 else ("PARTIAL" if present else "OPEN")
        elif b.get("closeWhen")=="runtime_enforced": state="CLOSED" if execution_exists and validation.returncode==0 else ("PARTIAL" if present else "OPEN")
        elif b.get("closeWhen")=="execution_runtime_exists": state="CLOSED" if execution_exists else "OPEN"
        elif b.get("closeWhen")=="evidence_runtime_exists": state="CLOSED" if evidence_exists else "OPEN"
        else: state="PARTIAL" if present else "OPEN"
        batches.append({"id":b["id"],"title":b["title"],"state":state,"present":present,"missing":missing})
    data={"schemaVersion":model["version"],"generatedFrom":"repository","sourceRevision":source_revision(),"status":"RELEASE_BLOCKED","truth":truth,"controls":controls,"counts":{"requirements":len(requirements),"tasks":len(tasks),"tests":len(mappings),"requiredTests":len(required_test_ids),"existingTests":sum(1 for tid in required_test_ids if tid in mapping_by_id and exists(mapping_by_id[tid]["path"])),"executions":0,"validEvidence":0,"verifiedRequirements":0},"batches":batches,"findings":findings,"workQueue":queue,"releaseReasons":[f["message"] for f in findings]}
    print(json.dumps(data,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
