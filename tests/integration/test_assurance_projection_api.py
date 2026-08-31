import hashlib
import hmac

import pytest

from apps.api import main


def signed(tenant_id: str) -> str:
    return hmac.new(main._AUTH_KEY.encode(), tenant_id.encode(), hashlib.sha256).hexdigest()


def test_partial_projection_is_unproven_without_missing_authoritative_dimensions():
    projection = main.build_partial_projection(
        "tenant-a",
        [{"execution_id": "exec-a"}],
        [{"evidence_id": "ev-a", "provenance_id": "prov-a"}],
        [{"verification_id": "ver-a"}],
    )
    assert projection.tenant_id == "tenant-a"
    assert projection.derived_status == "UNPROVEN"
    assert projection.execution_ref == "exec-a"
    assert projection.evidence_refs == ("ev-a",)
    assert projection.provenance_refs == ("prov-a",)
    assert projection.verification_refs == ("ver-a",)
    assert set(projection.unavailable_dimensions) == {"requirement", "implementation", "test_certification", "trust_root"}
    assert "UNPROVEN" in projection.assurance_assertion


def test_partial_projection_cannot_manufacture_proven_from_counts():
    projection = main.build_partial_projection(
        "tenant-a",
        [{"execution_id": "exec-a"}],
        [{"evidence_id": "ev-a", "provenance_id": "prov-a"}],
        [{"verification_id": "ver-a"}],
    )
    assert projection.derived_status != "PROVEN"


def test_partial_projection_is_tenant_bound_by_input_identity():
    projection = main.build_partial_projection("tenant-b", [], [], [])
    assert projection.tenant_id == "tenant-b"
    assert projection.derived_status == "UNPROVEN"


def test_missing_tenant_fails_closed():
    with pytest.raises(main.HTTPException) as exc:
        main.tenant(None, None)
    assert exc.value.status_code == 401


def test_invalid_tenant_signature_fails_closed():
    with pytest.raises(main.HTTPException) as exc:
        main.tenant("tenant-a", "0" * 64)
    assert exc.value.status_code == 401


def test_route_is_read_only_and_tenant_authenticated():
    route = next(r for r in main.app.routes if getattr(r, "path", None) == "/api/v1/assurance/projection")
    assert route.methods == {"GET"}
    assert "x_tinyd_tenant_id" in route.endpoint.__annotations__
    assert "x_tinyd_tenant_signature" in route.endpoint.__annotations__
