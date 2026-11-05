from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.api.auth import Tenant, require_scope, require_tenant
from apps.api.billing import create_checkout_session, report_meter_event, verify_webhook_signature
from apps.api.registry import get_package, list_packages, manifest_digest
from packages.runtime.src.engine import RuntimeEngine
from packages.runtime.src.ledger import PostgresEventLedger
from packages.runtime.src.journal import PostgresEventJournal, EventJournalError
from packages.runtime.src.journal_service import append_tenant_event

app = FastAPI(title="TinyD Control Plane API", version="1.3")
_database_url = os.getenv("DATABASE_URL", "").strip()
engine = RuntimeEngine(ledger=PostgresEventLedger(_database_url) if _database_url else None)
journal = PostgresEventJournal(_database_url) if _database_url else None


class WorkflowRun(BaseModel):
    workflow: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class ReplayRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)


class JournalAppendRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=200)
    aggregate_type: str = Field(min_length=1, max_length=100)
    aggregate_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: UUID | None = None
    agent_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None


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


def canonical_tenant_id(tenant: Tenant) -> UUID:
    return uuid5(NAMESPACE_URL, f"tinyd:tenant:{tenant.id}")


def emit(event: dict[str, Any]) -> dict[str, Any]:
    return engine.execute(event)


@app.get("/health")
def health():
    return {"status": "ok", "service": "tinyd-control-plane", "persistence": "postgres" if engine.ledger else "memory"}


@app.get("/v1/runtime/status")
def runtime_status(tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "events:read")
    if journal is not None:
        history = journal.tenant_history(canonical_tenant_id(tenant))
        return {
            "service": "tinyd-runtime",
            "mode": "connected",
            "persistence": "postgres",
            "execution_count": sum(1 for event in history if event.event_type == "workflow.requested"),
            "event_count": len(history),
            "replay_ready": False,
            "verification": "not_configured",
            "canonical_journal": "postgres_connected",
            "execution_store": "canonical_journal",
        }
    snapshot = engine.tenant_snapshot(tenant.id)
    return {
        "service": "tinyd-runtime",
        "mode": "development",
        "persistence": "memory",
        "execution_count": sum(1 for event in snapshot.values() if event.get("type") == "workflow.requested"),
        "event_count": len(snapshot),
        "replay_ready": any(event.get("type") == "workflow.requested" for event in snapshot.values()),
        "verification": "not_configured",
        "canonical_journal": "unavailable",
        "execution_store": "legacy_development_engine",
    }


@app.post("/v1/journal/events", status_code=201)
def append_journal_event(
    request: JournalAppendRequest,
    tenant: Tenant = Depends(require_tenant),
):
    require_scope(tenant, "events:write")
    if journal is None:
        raise HTTPException(status_code=503, detail="canonical PostgreSQL event journal is unavailable")
    tenant_uuid = canonical_tenant_id(tenant)
    try:
        event = append_tenant_event(
            journal,
            tenant_id=tenant_uuid,
            event_type=request.event_type,
            aggregate_type=request.aggregate_type,
            aggregate_id=request.aggregate_id,
            payload=request.payload,
            event_id=request.event_id,
            agent_id=request.agent_id,
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
        )
    except EventJournalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "appended", "event": event.model_dump(mode="json")}


@app.get("/v1/journal/events/{event_id}")
def get_journal_event(
    event_id: UUID,
    tenant: Tenant = Depends(require_tenant),
):
    require_scope(tenant, "events:read")
    if journal is None:
        raise HTTPException(status_code=503, detail="canonical PostgreSQL event journal is unavailable")
    tenant_uuid = uuid5(NAMESPACE_URL, f"tinyd:tenant:{tenant.id}")
    event = journal.get(event_id, tenant_uuid)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return {"event": event.model_dump(mode="json")}


@app.get("/v1/events")
def events(tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "events:read")
    if journal is not None:
        history = journal.tenant_history(canonical_tenant_id(tenant))
        return {
            "tenant_id": tenant.id,
            "events": [event.model_dump(mode="json") for event in history],
            "source": "canonical_journal",
        }
    return {
        "tenant_id": tenant.id,
        "events": list(engine.tenant_snapshot(tenant.id).values()),
        "source": "legacy_development_engine",
    }


@app.post("/v1/executions", status_code=201)
def run_workflow(request: WorkflowRun, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    semantic_request = {
        "tenant_id": tenant.id,
        "workflow": request.workflow,
        "payload": request.payload,
        "idempotency_key": request.idempotency_key,
    }
    legacy_id = event_id_for(request.workflow, semantic_request)
    if journal is not None:
        tenant_uuid = canonical_tenant_id(tenant)
        key = request.idempotency_key or hashlib.sha256(
            json.dumps(semantic_request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        canonical_event_id = uuid5(tenant_uuid, f"execution:{key}")
        aggregate_id = uuid5(tenant_uuid, f"workflow:{request.workflow}")
        already_persisted = journal.get(canonical_event_id, tenant_uuid) is not None
        try:
            persisted = append_tenant_event(
                journal,
                tenant_id=tenant_uuid,
                event_type="workflow.requested",
                aggregate_type="workflow_execution",
                aggregate_id=aggregate_id,
                payload={
                    "workflow": request.workflow,
                    "request_payload": request.payload,
                    "idempotency_key": key,
                },
                event_id=canonical_event_id,
                agent_id=uuid5(tenant_uuid, "tinyd:control-plane"),
                correlation_id=canonical_event_id,
            )
        except EventJournalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "status": "accepted",
            "event_id": str(persisted.event_id),
            "legacy_event_id": legacy_id,
            "idempotent": already_persisted,
            "event": persisted.model_dump(mode="json"),
            "persistence": "canonical_journal",
        }
    event = {
        "id": legacy_id,
        "type": "workflow.requested",
        "tenant_id": tenant.id,
        "workflow": request.workflow,
        "payload": request.payload,
        "timestamp": now(),
    }
    return {**emit(event), "event": event, "persistence": "legacy_development_engine"}


@app.post("/v1/replay")
def replay(request: ReplayRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "executions:write")
    if journal is not None:
        raise HTTPException(
            status_code=501,
            detail="canonical replay projection is not implemented; legacy replay is disabled for journal-backed executions",
        )
    event = engine.get(request.event_id)
    if event is None or event.get("tenant_id") != tenant.id:
        raise HTTPException(status_code=404, detail="event not found")
    replay_event = {
        **event,
        "id": replay_id_for(event["id"]),
        "type": "workflow.replayed",
        "replayed_from": event["id"],
        "timestamp": now(),
    }
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
    event = {
        "id": event_id_for("marketplace.install", {"tenant_id": tenant.id, "package_id": package["id"], "version": package["version"]}),
        "type": "marketplace.package.installed",
        "tenant_id": tenant.id,
        "package_id": package["id"],
        "version": package["version"],
        "manifest_digest": manifest_digest(package),
        "timestamp": now(),
    }
    emit(event)
    return {"status": "installed", "tenant_id": tenant.id, "package": package, "event_id": event["id"]}


@app.post("/v1/marketplace/usage", status_code=201)
def record_usage(request: UsageRequest, tenant: Tenant = Depends(require_tenant)):
    require_scope(tenant, "usage:write")
    package = get_package(request.package_id)
    if not package:
        raise HTTPException(status_code=404, detail="package not found")
    event = {
        "id": event_id_for("marketplace.usage", {"tenant_id": tenant.id, **request.model_dump()}),
        "type": "marketplace.usage.recorded",
        "tenant_id": tenant.id,
        **request.model_dump(),
        "timestamp": now(),
    }
    emit(event)
    meter = package.get("billing", {}).get("stripe_meter_event_name")
    if meter:
        customer_id = next(
            (e.get("stripe_customer_id") for e in reversed(list(engine.tenant_snapshot(tenant.id).values())) if e.get("type") == "billing.customer.linked"),
            None,
        )
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
    event = {
        "id": "bill_" + hashlib.sha256(payload).hexdigest()[:16],
        "type": "billing.webhook.received",
        "stripe_event_type": event_type,
        "tenant_id": tenant_id,
        "payload": data,
        "timestamp": now(),
    }
    emit(event)
    if tenant_id and obj.get("customer"):
        emit({
            "id": "cust_" + hashlib.sha256(f"{tenant_id}:{obj['customer']}".encode()).hexdigest()[:16],
            "type": "billing.customer.linked",
            "tenant_id": tenant_id,
            "stripe_customer_id": obj["customer"],
            "timestamp": now(),
        })
    return {"received": True, "event_id": event["id"]}
