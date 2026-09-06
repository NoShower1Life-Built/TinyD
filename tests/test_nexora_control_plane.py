import hashlib
import json

from fastapi.testclient import TestClient

from apps.api.main import app, engine


TEST_TOKEN = 'test-control-plane-token'
TEST_TENANT = 'test-tenant'
TEST_CONFIG = json.dumps(
    {
        hashlib.sha256(TEST_TOKEN.encode()).hexdigest(): {
            'tenant_id': TEST_TENANT,
            'scopes': ['executions:write'],
        }
    }
)

client = TestClient(app)


def setup_function():
    engine.state.clear()


def auth_headers():
    return {'Authorization': f'Bearer {TEST_TOKEN}'}


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_run_is_deterministic_and_idempotent(monkeypatch):
    monkeypatch.setenv('TINYD_TENANT_TOKENS', TEST_CONFIG)
    payload = {'workflow': 'nexora-check', 'payload': {'x': 1}}
    first = client.post('/v1/executions', json=payload, headers=auth_headers())
    second = client.post('/v1/executions', json=payload, headers=auth_headers())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()['event_id'] == second.json()['event_id']
    assert second.json()['idempotent'] is True
    assert client.get('/v1/runtime/status').json()['event_count'] == 1


def test_event_ids_are_tenant_scoped(monkeypatch):
    token_a = 'tenant-a-token'
    token_b = 'tenant-b-token'
    monkeypatch.setenv(
        'TINYD_TENANT_TOKENS',
        json.dumps(
            {
                hashlib.sha256(token_a.encode()).hexdigest(): {'tenant_id': 'tenant-a', 'scopes': ['executions:write']},
                hashlib.sha256(token_b.encode()).hexdigest(): {'tenant_id': 'tenant-b', 'scopes': ['executions:write']},
            }
        ),
    )
    payload = {'workflow': 'same-workflow', 'payload': {'x': 1}}
    a = client.post('/v1/executions', json=payload, headers={'Authorization': f'Bearer {token_a}'})
    b = client.post('/v1/executions', json=payload, headers={'Authorization': f'Bearer {token_b}'})
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()['event_id'] != b.json()['event_id']


def test_replay_requires_an_existing_event(monkeypatch):
    monkeypatch.setenv('TINYD_TENANT_TOKENS', TEST_CONFIG)
    missing = client.post('/v1/replay', json={'event_id': 'evt_missing'}, headers=auth_headers())
    assert missing.status_code == 404


def test_replay_preserves_original_event(monkeypatch):
    monkeypatch.setenv('TINYD_TENANT_TOKENS', TEST_CONFIG)
    created = client.post(
        '/v1/executions',
        json={'workflow': 'replay-check', 'payload': {}},
        headers=auth_headers(),
    )
    assert created.status_code == 201
    event_id = created.json()['event_id']
    original = engine.snapshot()[event_id]
    replayed = client.post('/v1/replay', json={'event_id': event_id}, headers=auth_headers())

    assert replayed.status_code == 200
    replay_event = replayed.json()['event']
    assert replay_event['replayed_from'] == event_id
    assert replay_event['id'] != event_id
    assert engine.snapshot()[event_id] == original
    assert engine.snapshot()[replay_event['id']]['type'] == 'workflow.replayed'
