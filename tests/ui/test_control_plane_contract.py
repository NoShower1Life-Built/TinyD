from pathlib import Path

ROOT = Path(__file__).parents[2]
HTML = (ROOT / "apps/control-plane/index.html").read_text()
JS = (ROOT / "apps/control-plane/app.js").read_text()


def test_api_values_use_text_nodes_not_inner_html():
    assert "innerHTML" not in JS
    assert "textContent" in JS


def test_assurance_status_is_explicitly_projection_bound():
    assert 'id="assuranceStatus"' in HTML
    assert "derived_status" in JS
    assert "summary.assurance_projection" in JS


def test_provenance_and_artifact_views_are_not_static_proof_claims():
    assert "Awaiting authoritative projection" in HTML
    assert "UNPROVEN until authoritative evidence exists" in HTML


def test_replay_distinguishes_recorded_from_independent():
    assert "Recorded verification" in JS
    assert "Independent replay execution: NOT ESTABLISHED" in JS


def test_execution_anchor_exists():
    assert 'id="executions"' in HTML


def test_tenant_bootstrap_declares_server_authenticated_source():
    assert 'name="tinyd-tenant-source"' in HTML
    assert "server-authenticated-bootstrap" in HTML


def test_workflow_control_remains_disabled():
    assert 'id="runBtn" disabled' in HTML
    assert "Kernel command API required" in JS


def test_api_base_is_deployment_configurable():
    assert 'name="tinyd-api-base" content=""' in HTML
    assert "window.location.origin" in JS
