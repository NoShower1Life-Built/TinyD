import base64
import hashlib
import json
import os
from uuid import UUID, uuid4

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
    history = event_journal.history(UUID(tenant_uuid), "run", UUID(run_id))
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


def test_expired_worker_lease_is_reclaimed_with_incremented_attempt():
    import psycopg

    tenant_id = f"worker-lease-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "sha256", "value": "lease-test"}},
    )
    assert response.status_code == 201, response.text

    first_worker = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"lease-a-{uuid4()}")
    first_claim = first_worker.claim_next()
    assert first_claim is not None
    assert first_claim["attempts"] == 1

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE tinyd_worker_tasks SET lease_until=NOW() - INTERVAL '1 second' WHERE event_id=%s",
            (first_claim["event_id"],),
        )

    second_worker = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"lease-b-{uuid4()}")
    reclaimed = second_worker.claim_next()
    assert reclaimed is not None
    assert reclaimed["event_id"] == first_claim["event_id"]
    assert reclaimed["attempts"] == 2


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

    browser_credential = base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")
    with client.websocket_connect(
        f"/v1/agent/runs/{run_id}/events",
        subprotocols=["tinyd.events.v1", f"tinyd.bearer.{browser_credential}"],
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



def test_reclaimed_lease_fences_stale_worker_commit():
    import psycopg
    from packages.runtime.src.worker import LeaseLost

    tenant_id = f"worker-fence-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "sha256", "value": "fence"}},
    )
    assert response.status_code == 201, response.text
    dsn = os.environ["DATABASE_URL"]
    first = DurableWorker(dsn, worker_id=f"fence-a-{uuid4()}")
    old_claim = first.claim_next()
    assert old_claim is not None
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE tinyd_worker_tasks SET lease_until=NOW() - INTERVAL '1 second' WHERE event_id=%s",
            (old_claim["event_id"],),
        )
    second = DurableWorker(dsn, worker_id=f"fence-b-{uuid4()}")
    new_claim = second.claim_next()
    assert new_claim is not None
    assert new_claim["lease_generation"] == old_claim["lease_generation"] + 1
    assert new_claim["attempts"] == old_claim["attempts"] + 1
    with pytest.raises(LeaseLost):
        first._commit_success(old_claim, {"operation": "sha256", "sha256": "stale"})
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT status, lease_generation, worker_id FROM tinyd_worker_tasks WHERE event_id=%s",
            (old_claim["event_id"],),
        ).fetchone()
    assert row[0] == "running"
    assert row[1] == new_claim["lease_generation"]
    assert row[2] == second.worker_id


def test_success_state_and_terminal_event_commit_atomically(monkeypatch):
    import psycopg

    tenant_id = f"worker-atomic-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "sha256", "value": "atomic"}},
    )
    assert response.status_code == 201, response.text
    worker = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"atomic-{uuid4()}")
    claim = worker.claim_next()
    assert claim is not None
    worker._append_started(claim)

    def fail_append(*args, **kwargs):
        raise RuntimeError("injected journal append failure")

    monkeypatch.setattr(worker.journal, "append", fail_append)
    with pytest.raises(RuntimeError, match="injected journal append failure"):
        worker._commit_success(claim, {"operation": "sha256", "sha256": "x"})

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT status, result FROM tinyd_worker_tasks WHERE event_id=%s",
            (claim["event_id"],),
        ).fetchone()
    assert row[0] == "running"
    assert row[1] is None
    history = event_journal.history(UUID(response.json()["event"]["tenant_id"]), "run", UUID(run_id))
    assert [event.event_type for event in history] == ["run.requested", "run.started"]


def test_expired_running_task_recovers_and_finishes_after_process_restart():
    import psycopg

    tenant_id = f"worker-recovery-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "canonicalize_json", "value": {"recovered": True}}},
    )
    assert response.status_code == 201, response.text
    first = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"crashed-{uuid4()}")
    first_claim = first.claim_next()
    assert first_claim is not None
    first._append_started(first_claim)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE tinyd_worker_tasks SET lease_until=NOW() - INTERVAL '1 second' WHERE event_id=%s",
            (first_claim["event_id"],),
        )

    restarted = DurableWorker(os.environ["DATABASE_URL"], worker_id=f"restarted-{uuid4()}")
    result = restarted.run_once()
    assert result is not None and result["status"] == "succeeded"
    history = event_journal.history(UUID(response.json()["event"]["tenant_id"]), "run", UUID(run_id))
    assert [event.event_type for event in history] == [
        "run.requested", "run.started", "run.started", "run.succeeded"
    ]
    assert history[-1].payload["lease_generation"] == 2



def test_concurrent_workers_claim_distinct_tasks():
    from concurrent.futures import ThreadPoolExecutor

    tenant_id = f"worker-concurrent-{uuid4()}"
    token = token_for(tenant_id)
    run_ids = [str(uuid4()), str(uuid4())]
    for run_id in run_ids:
        response = client.post(
            "/v1/agent/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"run_id": run_id, "payload": {"operation": "sha256", "value": run_id}},
        )
        assert response.status_code == 201, response.text

    dsn = os.environ["DATABASE_URL"]
    workers = [
        DurableWorker(dsn, worker_id=f"parallel-{uuid4()}"),
        DurableWorker(dsn, worker_id=f"parallel-{uuid4()}"),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda item: item.claim_next(), workers))
    assert all(claim is not None for claim in claims)
    assert len({claim["event_id"] for claim in claims}) == 2
    assert {claim["run_id"] for claim in claims} == {UUID(value) for value in run_ids}



def test_reconciles_legacy_terminal_row_missing_journal_event():
    import psycopg

    tenant_id = f"worker-reconcile-{uuid4()}"
    token = token_for(tenant_id)
    run_id = str(uuid4())
    response = client.post(
        "/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_id": run_id, "payload": {"operation": "sha256", "value": "legacy"}},
    )
    assert response.status_code == 201, response.text
    dsn = os.environ["DATABASE_URL"]
    legacy_worker = DurableWorker(dsn, worker_id=f"legacy-{uuid4()}")
    claim = legacy_worker.claim_next()
    assert claim is not None
    legacy_worker._append_started(claim)

    # Reproduce the old crash window: task result committed, terminal event absent.
    result = {"operation": "sha256", "sha256": "legacy-result"}
    with psycopg.connect(dsn) as conn:
        conn.execute(
            """
            UPDATE tinyd_worker_tasks
            SET status='succeeded', result=%s::jsonb, worker_id=NULL,
                lease_until=NULL, updated_at=NOW()
            WHERE event_id=%s
            """,
            (json.dumps(result), claim["event_id"]),
        )

    recovery_worker = DurableWorker(dsn, worker_id=f"reconciler-{uuid4()}")
    assert recovery_worker.claim_next() is None
    history = event_journal.history(UUID(response.json()["event"]["tenant_id"]), "run", UUID(run_id))
    assert [event.event_type for event in history] == [
        "run.requested", "run.started", "run.succeeded"
    ]
    assert history[-1].payload["recovered"] is True
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT status, result FROM tinyd_worker_tasks WHERE event_id=%s",
            (claim["event_id"],),
        ).fetchone()
    assert row[0] == "succeeded"
    assert row[1] == result
