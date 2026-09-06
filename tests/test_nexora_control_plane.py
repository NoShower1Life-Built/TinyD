from fastapi.testclient import TestClient

from apps.api.main import app, engine

client = TestClient(app)


def setup_function():
    engine.state.clear()


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_run_is_deterministic_for_same_input():
    payload = {'workflow': 'nexora-check', 'payload': {'x': 1}}
    first = client.post('/v1/executions', json=payload)
    second = client.post('/v1/executions', json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()['event_id'] == second.json()['event_id']
    assert client.get('/v1/runtime/status').json()['event_count'] == 1


def test_replay_requires_an_existing_event():
    missing = client.post('/v1/replay', json={'event_id': 'evt_missing'})
    assert missing.status_code == 404


def test_replay_existing_event():
    created = client.post('/v1/executions', json={'workflow': 'replay-check', 'payload': {}})
    event_id = created.json()['event_id']
    replayed = client.post('/v1/replay', json={'event_id': event_id})

    assert replayed.status_code == 200
    assert replayed.json()['event']['id'] == event_id
