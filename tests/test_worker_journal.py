import hashlib
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app, event_journal
from packages.runtime.src.worker import DurableWorker

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="durable worker integration requires PostgreSQL",
)

client = TestClient(app)


def token_for(tenant_id: str) -> str:
    token = f"worker-test:{tenant_id}"
    digest = hashlib.sha256(token.encode()).hexdigest()
    os.environ["TINYD_TENANT_TOKENS"] = json.dumps(
        {
            digest: {
                "tenant_id": tenant_id,
                "scopes": ["executions:write", "events:read", "workers:execute"],
            }
        }
    )
    return token


def test_worker_claims_journal_request_and_persists_transitions():
    tenant_id = f"worker-tenant-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "run_id": run_id,
            "payload": {"operation": "sha256", "value": {"b": 2, "a": 1}},
        },
    )
    assert response.status_code == 201, response.text

    worker = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"test-{uuid4()}")
    result = worker.run_once()

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["result"]["operation"] == "sha256"
    assert len(result["result"]["sha256"]) == 64

    tenant_uuid = response.json()["event"]["tenant_id"]
    history = event_journal.history(
        __import__("uuid").UUID(tenant_uuid), "run", __import__("uuid").UUID(run_id)
    )
    assert [event.event_type for event in history] == [
        "run.requested",
        "run.started",
        "run.succeeded",
    ]
    assert [event.sequence for event in history] == [1, 2, 3]
    assert worker.run_once() is None


def test_worker_records_unknown_operation_as_durable_failure():
    tenant_id = f"worker-failure-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "not-registered"}},
    )
    assert response.status_code == 201, response.text

    worker = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"test-{uuid4()}")
    result = worker.run_once()
    assert result is not None
    assert result["status"] == "failed"
    assert "NoHandlerRegistered" in result["error"]

    from uuid import UUID

    history = event_journal.history(
        UUID(response.json()["event"]["tenant_id"]), "run", UUID(run_id)
    )
    assert [event.event_type for event in history] == [
        "run.requested",
        "run.started",
        "run.failed",
    ]


def test_websocket_streams_persisted_events_only_for_authorized_tenant():
    tenant_id = f"worker-stream-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "canonicalize_json", "value": {"ok": True}}},
    )
    assert response.status_code == 201, response.text

    with client.websocket_connect(
        f"/v1/agent/runs/{run_id}/events",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        event = websocket.receive_json()
        assert event["event_type"] == "run.requested"
        assert event["tenant_id"] == response.json()["event"]["tenant_id"]

    read_only_token = f"read-only:{tenant_id}"
    digest = hashlib.sha256(read_only_token.encode()).hexdigest()
    os.environ["TINYD_TENANT_TOKENS"] = json.dumps(
        {digest: {"tenant_id": tenant_id, "scopes": ["executions:write"]}}
    )
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/v1/agent/runs/{run_id}/events",
            headers={"Authorization": f"Bearer {read_only_token}"},
        ) as websocket:
            websocket.receive_json()
