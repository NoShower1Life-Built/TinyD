from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from apps.api.auth import Tenant, require_scope, require_tenant
from apps.api.billing import create_checkout_session
from apps.api.registry import get_package, list_packages, manifest_digest
from packages.runtime.src.engine import RuntimeEngine

app = FastAPI(title="TinyD Control Plane API", version="1.2")
engine = RuntimeEngine()


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


def event_id_for(workflow: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"workflow": workflow, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()
    return "evt_" + hashlib.sha256(canonical).hexdigest()[:16]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(event: dict[str, Any]) -> dict[str, Any]:
    return engine.execute(event)


@app.get("/health")
def health():
    return {"status": "ok", "service": "tinyd-control-plane"}


@app.get("/v1/runtime/status")
def runtime_status():
    snapshot = engine.snapshot()
    return {"service": "tinyd-runtime", "mode": "connected", "execution_count": len(snapshot), "event_count": len(snapshot), "replay_ready": bool(snapshot), "verification": "manifest-backed"}


@app.get("/v1/events")
def events(tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "events:read")
    return {"tenant_id": tenant.id, "events": [e for e in engine.snapshot().values() if e.get("tenant_id") == tenant.id]}


@app.post("/v1/executions", status_code=201)
def run_workflow(request: WorkflowRun, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    event_id = event_id_for(request.workflow, request.payload)
    event = {"id": event_id, "type": "workflow.requested", "tenant_id": tenant.id, "workflow": request.workflow, "payload": request.payload, "timestamp": now()}
    result = emit(event)
    return {**result, "event": event}


@app.post("/v1/replay")
def replay(request: ReplayRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    event = engine.snapshot().get(request.event_id)
    if event is None or event.get("tenant_id") != tenant.id:
        raise HTTPException(status_code=404, detail="event not found")
    replay_event = {**event, "type": "workflow.replayed", "replayed_from": event["id"], "timestamp": now()}
    return {**emit(replay_event), "event": replay_event}


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
def marketplace_billing_webhook(payload: dict[str, Any]):
    event_type = payload.get("type", "unknown")
    event = {"id": "bill_" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16], "type": "billing.webhook.received", "stripe_event_type": event_type, "payload": payload, "timestamp": now()}
    emit(event)
    return {"received": True, "event_id": event["id"]}
