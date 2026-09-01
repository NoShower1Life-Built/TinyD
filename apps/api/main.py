from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from packages.runtime.src.engine import RuntimeEngine

app = FastAPI(title="Nexora Runtime API", version="1.1")
engine = RuntimeEngine()


class WorkflowRun(BaseModel):
    workflow: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class ReplayRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)


def event_id_for(workflow: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"workflow": workflow, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "evt_" + hashlib.sha256(canonical).hexdigest()[:16]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health():
    return {"status": "ok", "service": "nexora-runtime-api"}


@app.get("/v1/runtime/status")
def runtime_status():
    snapshot = engine.snapshot()
    return {
        "service": "nexora-runtime",
        "mode": "connected",
        "execution_count": len(snapshot),
        "event_count": len(snapshot),
        "replay_ready": bool(snapshot),
        "verification": "not_configured",
    }


@app.get("/v1/events")
def events():
    return {"events": list(engine.snapshot().values())}


@app.post("/v1/executions", status_code=201)
def run_workflow(request: WorkflowRun):
    event_id = event_id_for(request.workflow, request.payload)
    event = {
        "id": event_id,
        "type": "workflow.requested",
        "workflow": request.workflow,
        "payload": request.payload,
        "timestamp": now(),
    }
    result = engine.execute(event)
    return {**result, "event": event}


@app.post("/v1/replay", status_code=200)
def replay(request: ReplayRequest):
    event = engine.snapshot().get(request.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    result = engine.execute({**event, "type": "workflow.replayed", "replayed_from": event["id"]})
    return {**result, "event": event}
