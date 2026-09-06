from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.api.auth import Tenant, require_scope, require_tenant
from apps.api.billing import create_checkout_session, report_meter_event, verify_webhook_signature
from apps.api.registry import get_package, list_packages, manifest_digest
from packages.runtime.src.engine import RuntimeEngine

app = FastAPI(title="TinyD Control Plane API", version="1.3")
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


def replay_id_for(event_id: str) -> str:
    return "rpl_" + hashlib.sha256(event_id.encode()).hexdigest()[:16]


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
    event = {"id": event_id_for(request.workflow, {"tenant_id": tenant.id, "payload": request.payload}), "type": "workflow.requested", "tenant_id": tenant.id, "workflow": request.workflow, "payload": request.payload, "timestamp": now()}
    return {**emit(event), "event": event}


@app.post("/v1/replay")
def replay(request: ReplayRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    event = engine.snapshot().get(request.event_id)
    if event is None or event.get("tenant_id") != tenant.id:
        raise HTTPException(status_code=404, detail="event not found")
    replay_event = {**event, "id": replay_id_for(event["id"]), "type": "workflow.replayed", "replayed_from": event["id"], "timestamp": now()}
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
    meter = package.get("billing", {}).get("stripe_meter_event_name")
    if meter:
        customer_id = next((e.get("stripe_customer_id") for e in reversed(list(engine.snapshot().values())) if e.get("type") == "billing.customer.linked" and e.get("tenant_id") == tenant.id), None)
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
