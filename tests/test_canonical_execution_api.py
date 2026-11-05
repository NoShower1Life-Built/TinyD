import hashlib
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app, journal


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or journal is None,
    reason="DATABASE_URL must be configured before importing the API for journal integration tests",
)

client = TestClient(app)


def _headers(tenant_id: str) -> dict[str, str]:
    token = f"canonical-journal-test-{tenant_id}"
    configured = {
        hashlib.sha256(token.encode()).hexdigest(): {
            "tenant_id": tenant_id,
            "scopes": ["executions:write", "events:read"],
        }
    }
    os.environ["TINYD_TENANT_TOKENS"] = json.dumps(configured)
    return {"Authorization": f"Bearer {token}"}


def test_execution_submission_is_persisted_in_canonical_journal():
    tenant_id = f"journal-integration-{uuid4()}"
    headers = _headers(tenant_id)
    idempotency_key = str(uuid4())
    body = {
        "workflow": "build-lint-analysis",
        "payload": {"repository": "org/repo", "revision": "a" * 40},
        "idempotency_key": idempotency_key,
    }

    first = client.post("/v1/executions", json=body, headers=headers)
    repeated = client.post("/v1/executions", json=body, headers=headers)

    assert first.status_code == 201, first.text
    assert repeated.status_code == 201, repeated.text
    assert first.json()["persistence"] == "canonical_journal"
    assert first.json()["event_id"] == repeated.json()["event_id"]
    assert repeated.json()["idempotent"] is True

    event_id = first.json()["event_id"]
    event_response = client.get(f"/v1/journal/events/{event_id}", headers=headers)
    assert event_response.status_code == 200, event_response.text
    assert event_response.json()["event"]["event_type"] == "workflow.requested"

    events_response = client.get("/v1/events", headers=headers)
    assert events_response.status_code == 200, events_response.text
    assert events_response.json()["source"] == "canonical_journal"
    assert any(event["event_id"] == event_id for event in events_response.json()["events"])


def test_canonical_execution_events_are_tenant_isolated():
    tenant_a = f"journal-tenant-a-{uuid4()}"
    tenant_b = f"journal-tenant-b-{uuid4()}"
    headers_a = _headers(tenant_a)
    created = client.post(
        "/v1/executions",
        json={
            "workflow": "tenant-isolation-check",
            "payload": {"revision": "b" * 40},
            "idempotency_key": str(uuid4()),
        },
        headers=headers_a,
    )
    assert created.status_code == 201, created.text

    headers_b = _headers(tenant_b)
    response = client.get(
        f"/v1/journal/events/{created.json()['event_id']}",
        headers=headers_b,
    )
    assert response.status_code == 404
