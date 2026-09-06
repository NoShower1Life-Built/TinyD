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
            'scopes': ['execution:write', 'replay:write'],
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


def test_run_is_deterministic_for_same_input(monkeypatch):
    monkeypatch.setenv('TINYD_TENANT_TOKENS', TEST_CONFIG)
    payload = {'workflow': 'nexora-check', 'payload': {'x': 1}}
    first = client.post('/v1/executions', json=payload, headers=auth_headers())
    second = client.post('/v1/executions', json=payload, headers=auth_headers())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()['event_id'] == second.json()['event_id']
    assert client.get('/v1/runtime/status').json()['event_count'] == 1


def test_replay_requires_an_existing_event(monkeypatch):
    monkeypatch.setenv('TINYD_TENANT_TOKENS', TEST_CONFIG)
    missing = client.post('/v1/replay', json={'event_id': 'evt_missing'}, headers=auth_headers())
    assert missing.status_code == 404


def test_replay_existing_event(monkeypatch):
    monkeypatch.setenv('TINYD_TENANT_TOKENS', TEST_CONFIG)
    created = client.post(
        '/v1/executions',
        json={'workflow': 'replay-check', 'payload': {}},
        headers=auth_headers(),
    )
    assert created.status_code == 201
    event_id = created.json()['event_id']
    replayed = client.post('/v1/replay', json={'event_id': event_id}, headers=auth_headers())

    assert replayed.status_code == 200
    assert replayed.json()['event']['id'] == event_id
