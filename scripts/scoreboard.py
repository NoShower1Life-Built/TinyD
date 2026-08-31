#!/usr/bin/env python3
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
def run_tests():
    result=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p","test_*.py","-v"],cwd=ROOT,text=True,capture_output=True)
    return result.returncode==0,(result.stdout+result.stderr).strip()
def runtime_state(revision):
    db=ROOT/"runtime"/"execution.db"
    if not db.exists(): return [],0
    from execution import ExecutionLedger
    records=list(ExecutionLedger(db).all())
    return records,sum(1 for r in records if r.state.value=="SUCCEEDED" and r.source_revision==revision)
def evidence_state(revision, executions):
    path=ROOT/"runtime"/"evidence.jsonl"
    if not path.exists(): return [],0
    from evidence import EvidenceLedger
    records=EvidenceLedger(path).records(); execution_ids={r.execution_id for r in executions if r.state.value=="SUCCEEDED" and r.source_revision==revision}
    valid=[e for e in records if e.source_revision==revision and e.execution_id in execution_ids]
    return records,len(valid)
def main():
    try:
        model=load("scoreboard-model.json"); requirements=load("requirements.json")["requirements"]; tasks=load("tasks.json")["tasks"]
        mappings=json.loads((ROOT/"tests"/"mappings.json").read_text(encoding="utf-8"))["tests"]
        queue=json.loads(subprocess.check_output([sys.executable,str(ROOT/"scripts/plan.py")],cwd=ROOT,text=True))["queue"]
        validation=subprocess.run([sys.executable,str(ROOT/"scripts/control_validate.py")],cwd=ROOT,text=True,capture_output=True)
        tests_passed,test_output=run_tests(); revision=source_revision(); executions,successful=runtime_state(revision); evidence,valid_evidence=evidence_state(revision,executions)
    except Exception as exc:
        print(f"SCOREBOARD: FAIL: {exc}"); return 1
    required_test_ids={tid for r in requirements for tid in r.get("tests",[])}; mapping_by_id={m["id"]:m for m in mappings}
    required_tests_exist=bool(required_test_ids) and all(tid in mapping_by_id and exists(mapping_by_id[tid]["path"]) for tid in required_test_ids)
    implementation_complete=all(all(exists(p) for p in r.get("implementation",[])) for r in requirements if r.get("required"))
    dependencies_satisfied=not any(x["state"]=="BLOCKED" for x in queue)
    execution_exists=exists("execution"); evidence_exists=exists("evidence")
    controls={"requirement_exists":bool(requirements),"implementation_complete":implementation_complete,"dependencies_satisfied":dependencies_satisfied,"required_tests_exist":required_tests_exist,"required_tests_pass":tests_passed and required_tests_exist,"execution_exists":execution_exists,"evidence_exists":evidence_exists,"execution_records_exist":bool(executions),"successful_execution_exists":successful>0,"evidence_valid":valid_evidence>0,"evidence_matches_source":valid_evidence>0,"no_blocking_findings":False}
    findings=[]
    if validation.returncode!=0: findings.append({"severity":"CRITICAL","id":"control_validation_failed","message":validation.stdout.strip() or validation.stderr.strip()})
    if not tests_passed: findings.append({"severity":"CRITICAL","id":"required_tests_failed","message":"Executable control tests did not pass."})
    if not dependencies_satisfied: findings.append({"severity":"HIGH","id":"dependencies_incomplete","message":"The ordered work queue contains blocked tasks."})
    if not executions: findings.append({"severity":"CRITICAL","id":"execution_records_missing","message":"No authoritative execution records exist for the current runtime state."})
    if not successful: findings.append({"severity":"CRITICAL","id":"successful_execution_missing","message":"No successful execution is proven for the current source revision."})
    if not valid_evidence: findings.append({"severity":"CRITICAL","id":"valid_evidence_missing","message":"No evidence is bound to a successful execution on the current source revision."})
    controls["no_blocking_findings"]=not any(f["severity"]=="CRITICAL" for f in findings)
    truth={"DEFINED":bool(requirements and tasks),"IMPLEMENTED":implementation_complete,"TESTED":controls["required_tests_pass"],"EXECUTED":successful>0,"EVIDENCED":valid_evidence>0,"VERIFIED":False,"CURRENT":valid_evidence>0,"RELEASEABLE":False}
    batches=[]
    for b in model["batches"]:
        present=[p for p in b.get("requiredPaths",[]) if exists(p)]; missing=[p for p in b.get("requiredPaths",[]) if not exists(p)]
        if b.get("closeWhen")=="control_validation_passes": state="CLOSED" if validation.returncode==0 and tests_passed else ("PARTIAL" if present else "OPEN")
        elif b.get("closeWhen")=="runtime_enforced": state="CLOSED" if execution_exists and validation.returncode==0 and tests_passed else ("PARTIAL" if present else "OPEN")
        elif b.get("closeWhen")=="execution_runtime_exists": state="CLOSED" if successful>0 else "OPEN"
        elif b.get("closeWhen")=="evidence_runtime_exists": state="CLOSED" if valid_evidence>0 else "OPEN"
        else: state="PARTIAL" if present else "OPEN"
        batches.append({"id":b["id"],"title":b["title"],"state":state,"present":present,"missing":missing})
    data={"schemaVersion":model["version"],"generatedFrom":"repository","sourceRevision":revision,"status":"RELEASE_BLOCKED","truth":truth,"controls":controls,"counts":{"requirements":len(requirements),"tasks":len(tasks),"tests":len(mappings),"executions":len(executions),"successfulExecutions":successful,"evidence":len(evidence),"validEvidence":valid_evidence},"batches":batches,"findings":findings,"workQueue":queue,"testRun":{"passed":tests_passed,"output":test_output},"releaseReasons":[f["message"] for f in findings]}
    print(json.dumps(data,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
