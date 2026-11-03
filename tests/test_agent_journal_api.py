import hashlib
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="canonical agent journal integration requires PostgreSQL",
)

client = TestClient(app)


def token_for(tenant_id: str) -> str:
    token = f"test-token:{tenant_id}"
    digest = hashlib.sha256(token.encode()).hexdigest()
    os.environ["TINYD_TENANT_TOKENS"] = json.dumps(
        {digest: {"tenant_id": tenant_id, "scopes": ["executions:write"]}}
    )
    return token


def submit(token: str, run_id: str, payload: dict):
    return client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": payload},
    )


def test_agent_run_is_persisted_and_idempotent(monkeypatch):
    tenant_id = "agent-tenant-a"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    payload = {"intent": "classify", "input": {"record_id": "r-17"}}

    first = submit(token, run_id, payload)
    second = submit(token, run_id, payload)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["event"]["event_id"] == second.json()["event"]["event_id"]
    assert second.json()["idempotent"] is True
    assert second.json()["event"]["payload"] == payload


def test_agent_run_id_collision_is_rejected(monkeypatch):
    token = token_for("agent-tenant-collision")
    run_id = str(uuid4())

    first = submit(token, run_id, {"intent": "summarize"})
    conflicting = submit(token, run_id, {"intent": "delete"})

    assert first.status_code == 201, first.text
    assert conflicting.status_code == 409
    assert "different content" in conflicting.json()["detail"]


def test_same_run_id_is_isolated_across_tenants(monkeypatch):
    run_id = str(uuid4())
    token_a = token_for("agent-tenant-a")
    first = submit(token_a, run_id, {"intent": "summarize"})
    assert first.status_code == 201, first.text

    token_b = token_for("agent-tenant-b")
    second = submit(token_b, run_id, {"intent": "summarize"})

    assert second.status_code == 201, second.text
    assert first.json()["event"]["event_id"] != second.json()["event"]["event_id"]
    assert first.json()["event"]["tenant_id"] != second.json()["event"]["tenant_id"]


def test_agent_run_requires_execution_scope(monkeypatch):
    token = "test-token:agent-read-only"
    digest = hashlib.sha256(token.encode()).hexdigest()
    monkeypatch.setenv(
        "TINYD_TENANT_TOKENS",
        json.dumps({digest: {"tenant_id": "agent-read-only", "scopes": ["events:read"]}}),
    )
    response = submit(token, str(uuid4()), {"intent": "summarize"})
    assert response.status_code == 403
