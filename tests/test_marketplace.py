from fastapi.testclient import TestClient

from apps.api.main import app, engine

client = TestClient(app)


def setup_function():
    engine.state.clear()


def test_catalog_is_manifest_backed():
    response = client.get('/v1/marketplace/packages')
    assert response.status_code == 200
    data = response.json()
    assert data['registry'] == 'repository-manifest'
    assert {p['id'] for p in data['packages']} >= {'tinyd.deterministic-research-agent', 'tinyd.incident-response-dag'}


def test_package_exposes_manifest_digest():
    response = client.get('/v1/marketplace/packages/tinyd.deterministic-research-agent')
    assert response.status_code == 200
    assert len(response.json()['manifest_digest']) == 64


def test_install_requires_tenant_authentication():
    response = client.post('/v1/marketplace/packages/tinyd.deterministic-research-agent/install')
    assert response.status_code == 401
