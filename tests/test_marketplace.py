import hashlib
import hmac
import json
import os
import time

from fastapi.testclient import TestClient

from apps.api.billing import verify_webhook_signature
from apps.api.main import app, engine

client = TestClient(app)


def setup_function():
    engine.state.clear()
    os.environ.pop("TINYD_TENANT_TOKENS", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)


def tenant_token(scopes=None):
    token = "tinyd-test-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    os.environ["TINYD_TENANT_TOKENS"] = json.dumps({token_hash: {"tenant_id": "tenant-test", "scopes": scopes or []}})
    return token


def test_catalog_is_manifest_backed():
    response = client.get("/v1/marketplace/packages")
    assert response.status_code == 200
    data = response.json()
    assert data["registry"] == "repository-manifest"
    assert {p["id"] for p in data["packages"]} >= {
        "tinyd.deterministic-research-agent",
        "tinyd.incident-response-dag",
    }


def test_package_exposes_manifest_digest():
    response = client.get("/v1/marketplace/packages/tinyd.deterministic-research-agent")
    assert response.status_code == 200
    assert len(response.json()["manifest_digest"]) == 64


def test_install_requires_tenant_authentication():
    response = client.post("/v1/marketplace/packages/tinyd.deterministic-research-agent/install")
    assert response.status_code == 401


def test_install_enforces_scope_and_records_tenant_event():
    token = tenant_token(["marketplace:install"])
    response = client.post(
        "/v1/marketplace/packages/tinyd.deterministic-research-agent/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["tenant_id"] == "tenant-test"
    events = client.get(
        "/v1/events", headers={"Authorization": f"Bearer {tenant_token(['events:read'])}"}
    )
    assert events.status_code == 200
    assert any(e["type"] == "marketplace.package.installed" for e in events.json()["events"])


def test_webhook_signature_accepts_valid_payload_and_rejects_tampering(monkeypatch):
    secret = "whsec_test"
    payload = json.dumps({"id": "evt_test", "type": "checkout.session.completed"}, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    signature = f"t={timestamp},v1={digest}"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)

    assert verify_webhook_signature(payload, signature)["id"] == "evt_test"

    try:
        verify_webhook_signature(payload + b"x", signature)
    except RuntimeError as exc:
        assert "invalid Stripe webhook signature" in str(exc)
    else:
        raise AssertionError("tampered webhook payload was accepted")


def test_webhook_endpoint_requires_valid_signature(monkeypatch):
    secret = "whsec_test"
    payload = json.dumps(
        {
            "id": "evt_checkout",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_test", "metadata": {"tenant_id": "tenant-test"}}},
        },
        separators=(",", ":"),
    ).encode()
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)

    response = client.post(
        "/v1/marketplace/billing/webhook",
        content=payload,
        headers={"stripe-signature": f"t={timestamp},v1={digest}"},
    )
    assert response.status_code == 200
    assert response.json()["received"] is True
    assert any(e["type"] == "billing.customer.linked" for e in engine.snapshot().values())

    bad = client.post(
        "/v1/marketplace/billing/webhook",
        content=payload,
        headers={"stripe-signature": f"t={timestamp},v1={'0' * 64}"},
    )
    assert bad.status_code == 400


def test_usage_records_tenant_boundary_without_stripe_customer():
    token = tenant_token(["usage:write"])
    response = client.post(
        "/v1/marketplace/usage",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "package_id": "tinyd.incident-response-dag",
            "quantity": 1,
            "unit": "execution",
        },
    )
    assert response.status_code == 201
    assert response.json()["tenant_id"] == "tenant-test"
