from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from apps.api.auth import Tenant, _token_map, require_scope, require_tenant
from apps.api.billing import create_checkout_session, report_meter_event, verify_webhook_signature
from apps.api.registry import get_package, list_packages, manifest_digest
from packages.runtime.src.engine import RuntimeEngine
from packages.runtime.src.ledger import PostgresEventLedger
from packages.contracts.src.envelope import EventEnvelope, EventIntegrity
from packages.runtime.src.journal import EventIntegrityError, EventSequenceConflict, PostgresEventJournal
from packages.runtime.src.worker import DurableWorker

app = FastAPI(title="TinyD Control Plane API", version="1.3")
_database_url = os.getenv("DATABASE_URL", "").strip()
engine = RuntimeEngine(ledger=PostgresEventLedger(_database_url) if _database_url else None)
event_journal = PostgresEventJournal(_database_url) if _database_url else None


class WorkflowRun(BaseModel):
    workflow: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class ReplayRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)


class UsageRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=1_000_000)
    unit: str = Field(min_length=1, max_length=50)


class CheckoutRequest(BaseModel):
    package_id: str
    version: str | None = None
    success_url: str
    cancel_url: str


class AgentRunRequest(BaseModel):
    run_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)


def event_id_for(workflow: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"workflow": workflow, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()
    return "evt_" + hashlib.sha256(canonical).hexdigest()[:16]


def replay_id_for(event_id: str) -> str:
    return "rpl_" + hashlib.sha256(event_id.encode()).hexdigest()[:16]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(event: dict[str, Any]) -> dict[str, Any]:
    return engine.execute(event)


@app.get("/health")
def health():
    return {"status": "ok", "service": "tinyd-control-plane", "persistence": "postgres" if engine.ledger else "memory"}


@app.get("/v1/runtime/status")
def runtime_status():
    snapshot = engine.snapshot()
    return {"service": "tinyd-runtime", "mode": "connected", "persistence": "postgres" if engine.ledger else "memory", "execution_count": len(snapshot), "event_count": len(snapshot), "replay_ready": bool(snapshot), "verification": "manifest-backed"}


@app.get("/v1/events")
def events(tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "events:read")
    return {"tenant_id": tenant.id, "events": list(engine.tenant_snapshot(tenant.id).values())}


@app.post("/v1/executions", status_code=201)
def run_workflow(request: WorkflowRun, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    event = {"id": event_id_for(request.workflow, {"tenant_id": tenant.id, "payload": request.payload}), "type": "workflow.requested", "tenant_id": tenant.id, "workflow": request.workflow, "payload": request.payload, "timestamp": now()}
    return {**emit(event), "event": event}


@app.post("/v1/replay")
def replay(request: ReplayRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    event = engine.get(request.event_id)
    if event is None or event.get("tenant_id") != tenant.id:
        raise HTTPException(status_code=404, detail="event not found")
    replay_event = {**event, "id": replay_id_for(event["id"]), "type": "workflow.replayed", "replayed_from": event["id"], "timestamp": now()}
    return {**emit(replay_event), "event": replay_event}


@app.post("/v1/agent/runs", status_code=201)
def submit_agent_run(request: AgentRunRequest, tenant: Tenant = Depends(require_tenant)):
    """Persist an agent run request to the canonical journal; never fall back to memory."""
    require_scope(tenant, "executions:write")
    if event_journal is None:
        raise HTTPException(status_code=503, detail="canonical PostgreSQL event journal is not configured")

    tenant_uuid = uuid5(NAMESPACE_URL, f"tinyd:tenant:{tenant.id}")
    agent_uuid = uuid5(NAMESPACE_URL, "tinyd:agent:default")
    event_id = uuid5(tenant_uuid, f"tinyd:run:{request.run_id}:v1")

    existing = event_journal.get(event_id, tenant_uuid)
    if existing is not None:
        if existing.payload != request.payload or existing.run_id != request.run_id:
            raise HTTPException(status_code=409, detail="run_id already exists with different content")
        return {
            "status": "accepted",
            "idempotent": True,
            "tenant_id": tenant.id,
            "event": existing.model_dump(mode="json"),
        }

    event = EventEnvelope(
        event_id=event_id,
        event_type="run.requested",
        event_version=1,
        tenant_id=tenant_uuid,
        agent_id=agent_uuid,
        run_id=request.run_id,
        correlation_id=uuid5(request.run_id, "tinyd:correlation:v1"),
        aggregate_type="run",
        aggregate_id=request.run_id,
        sequence=1,
        producer="tinyd-agent-api",
        payload=request.payload,
        integrity=EventIntegrity(previous_digest=None, digest="pending"),
    )
    event = event.model_copy(update={
        "integrity": EventIntegrity(
            previous_digest=None,
            digest=event_journal.calculate_digest(event, None),
        )
    })
    try:
        persisted = event_journal.append(event)
    except EventIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EventSequenceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "status": "accepted",
        "idempotent": False,
        "tenant_id": tenant.id,
        "event": persisted.model_dump(mode="json"),
    }



@app.websocket("/v1/agent/runs/{run_id}/events")
async def agent_run_events(websocket: WebSocket, run_id: UUID, after_sequence: int = 0):
    """Stream persisted run events over WebSocket; PostgreSQL journal remains authoritative."""
    authorization = websocket.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        await websocket.close(code=4401, reason="bearer token required")
        return
    token = authorization[7:].strip()
    token_digest = hashlib.sha256(token.encode()).hexdigest()
    identity = _token_map().get(token_digest)
    if not isinstance(identity, dict):
        await websocket.close(code=4401, reason="invalid tenant credentials")
        return
    scopes = identity.get("scopes", [])
    tenant_id = identity.get("tenant_id")
    if not isinstance(tenant_id, str) or not isinstance(scopes, list):
        await websocket.close(code=4401, reason="invalid tenant credentials")
        return
    if "events:read" not in scopes:
        await websocket.close(code=4403, reason="missing scope: events:read")
        return
    if event_journal is None:
        await websocket.close(code=1013, reason="canonical PostgreSQL journal is not configured")
        return
    tenant_uuid = uuid5(NAMESPACE_URL, f"tinyd:tenant:{tenant_id.strip()}")
    await websocket.accept()
    cursor = max(0, after_sequence)
    try:
        while True:
            history = event_journal.history(tenant_uuid, "run", run_id)
            for event in history:
                if event.sequence > cursor:
                    await websocket.send_json(event.model_dump(mode="json"))
                    cursor = event.sequence
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return


@app.post("/v1/agent/worker/run-once")
def agent_worker_run_once(tenant: Tenant = Depends(require_tenant)):
    """Run one durable queue item; scope is restricted to operational operators."""
    require_scope(tenant, "workers:execute")
    if event_journal is None:
        raise HTTPException(status_code=503, detail="canonical PostgreSQL event journal is not configured")
    try:
        result = DurableWorker(_database_url).run_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="worker execution failed") from exc
    return {"status": "idle"} if result is None else result


@app.get("/v1/marketplace/packages")
def marketplace_packages(query: str = Query(default=""), category: str = Query(default="")):
    packages = list_packages(query=query, category=category)
    return {"packages": packages, "count": len(packages), "registry": "repository-manifest"}


@app.get("/v1/marketplace/packages/{package_id}")
def marketplace_package(package_id: str, version: str | None = None):
    package = get_package(package_id, version)
    if not package:
        raise HTTPException(status_code=404, detail="package not found")
    return {"package": package, "manifest_digest": manifest_digest(package)}


@app.post("/v1/marketplace/packages/{package_id}/install", status_code=201)
def install_package(package_id: str, version: str | None = None, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "marketplace:install")
    package = get_package(package_id, version)
    if not package:
        raise HTTPException(status_code=404, detail="package not found")
    if package.get("verification", {}).get("status") != "verified":
        raise HTTPException(status_code=409, detail="package verification gate has not passed")
    event = {"id": event_id_for("marketplace.install", {"tenant_id": tenant.id, "package_id": package["id"], "version": package["version"]}), "type": "marketplace.package.installed", "tenant_id": tenant.id, "package_id": package["id"], "version": package["version"], "manifest_digest": manifest_digest(package), "timestamp": now()}
    emit(event)
    return {"status": "installed", "tenant_id": tenant.id, "package": package, "event_id": event["id"]}


@app.post("/v1/marketplace/usage", status_code=201)
def record_usage(request: UsageRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "usage:write")
    package = get_package(request.package_id)
    if not package:
        raise HTTPException(status_code=404, detail="package not found")
    event = {"id": event_id_for("marketplace.usage", {"tenant_id": tenant.id, **request.model_dump()}), "type": "marketplace.usage.recorded", "tenant_id": tenant.id, **request.model_dump(), "timestamp": now()}
    emit(event)
    meter = package.get("billing", {}).get("stripe_meter_event_name")
    if meter:
        customer_id = next((e.get("stripe_customer_id") for e in reversed(list(engine.tenant_snapshot(tenant.id).values())) if e.get("type") == "billing.customer.linked"), None)
        if customer_id:
            try:
                report_meter_event(meter_event_name=meter, customer_id=customer_id, value=request.quantity, identifier=event["id"])
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "recorded", "tenant_id": tenant.id, "event_id": event["id"], "usage": request.model_dump()}


@app.post("/v1/marketplace/billing/checkout")
def marketplace_checkout(request: CheckoutRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "billing:write")
    package = get_package(request.package_id, request.version)
    if not package:
        raise HTTPException(status_code=404, detail="package not found")
    try:
        return create_checkout_session(tenant_id=tenant.id, package=package, success_url=request.success_url, cancel_url=request.cancel_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/marketplace/billing/webhook")
async def marketplace_billing_webhook(request: Request):
    try:
        payload = await request.body()
        data = verify_webhook_signature(payload, request.headers.get("stripe-signature"))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    event_type = data.get("type", "unknown")
    obj = data.get("data", {}).get("object", {})
    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail="invalid Stripe webhook object")
    metadata = obj.get("metadata", {}) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    tenant_id = metadata.get("tenant_id") or data.get("client_reference_id")
    event = {"id": "bill_" + hashlib.sha256(payload).hexdigest()[:16], "type": "billing.webhook.received", "stripe_event_type": event_type, "tenant_id": tenant_id, "payload": data, "timestamp": now()}
    emit(event)
    if tenant_id and obj.get("customer"):
        emit({"id": "cust_" + hashlib.sha256(f"{tenant_id}:{obj['customer']}".encode()).hexdigest()[:16], "type": "billing.customer.linked", "tenant_id": tenant_id, "stripe_customer_id": obj["customer"], "timestamp": now()})
    return {"received": True, "event_id": event["id"]}
