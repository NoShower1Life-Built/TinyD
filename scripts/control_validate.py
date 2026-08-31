#!/usr/bin/env python3
"""Validate canonical TinyD control-model invariants."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTROL=ROOT/"control"
def load(path:Path): return json.loads(path.read_text(encoding="utf-8"))
def fail(errors:list[str], message:str): errors.append(message)
def main()->int:
    errors=[]
    model=load(CONTROL/"control-model.json")
    states=load(CONTROL/"state-machine.json")
    requirements=load(CONTROL/"requirements.json")["requirements"]
    tasks=load(CONTROL/"tasks.json")["tasks"]
    mappings=load(ROOT/"tests"/"mappings.json")["tests"]
    req_ids={r["id"] for r in requirements}; task_ids={t["id"] for t in tasks}; mapping_by_id={m["id"]:m for m in mappings}
    for r in requirements:
        if not r.get("owner"): fail(errors,f"requirement {r['id']} has no owner")
        for p in r.get("implementation",[]):
            if not (ROOT/p).is_file(): fail(errors,f"requirement {r['id']} implementation missing: {p}")
        tests=r.get("tests",[])
        if not tests: fail(errors,f"requirement {r['id']} has no test")
        for tid in tests:
            m=mapping_by_id.get(tid)
            if not m: fail(errors,f"requirement {r['id']} references unknown test {tid}")
            elif not (ROOT/m["path"]).is_file(): fail(errors,f"test {tid} has no executable file: {m['path']}")
    for t in tasks:
        if "dependsOn" not in t: fail(errors,f"task {t['id']} does not declare dependencies")
        for d in t.get("dependsOn",[]):
            if d not in task_ids: fail(errors,f"task {t['id']} references missing dependency {d}")
        for rid in t.get("requirements",[]):
            if rid not in req_ids: fail(errors,f"task {t['id']} references unknown requirement {rid}")
        if t.get("state")=="COMPLETE":
            for d in t.get("dependsOn",[]):
                if next(x for x in tasks if x["id"]==d).get("state")!="COMPLETE": fail(errors,f"task {t['id']} is complete while dependency {d} is incomplete")
    allowed=states["allowedTransitions"]
    for source,dests in allowed.items():
        if source not in states["executionStates"]: fail(errors,f"state {source} is not declared")
        for dest in dests:
            if dest not in states["executionStates"]: fail(errors,f"transition {source}->{dest} uses undeclared state {dest}")
    for shortcut in states.get("forbiddenShortcuts",[]):
        source,dest=shortcut.split("->",1)
        if dest in allowed.get(source,[]): fail(errors,f"forbidden shortcut is allowed: {shortcut}")
    if not model.get("invariants"): fail(errors,"canonical invariant set is empty")
    if not model.get("verification",{}).get("requiredPredicates"): fail(errors,"verification predicate set is empty")
    if not model.get("readiness",{}).get("requiredPredicates"): fail(errors,"readiness predicate set is empty")
    if model.get("releaseGate",{}).get("manualOverrideAllowed",True): fail(errors,"release gate permits manual override")
    if model.get("releaseGate",{}).get("failClosed") is not True: fail(errors,"release gate is not fail-closed")
    if errors:
        print("CONTROL VALIDATION: FAIL")
        for e in errors: print(f"- {e}")
        return 1
    print(f"CONTROL VALIDATION: PASS requirements={len(requirements)} tasks={len(tasks)} tests={len(mappings)}")
    return 0
if __name__=="__main__": sys.exit(main())
