import hashlib
import hmac
import importlib
import os

os.environ.setdefault("TINYD_TENANT_SIGNING_KEY", "test-only-signing-key")

api = importlib.import_module("apps.api.main")


def signature(tenant: str) -> str:
    return hmac.new(b"test-only-signing-key", tenant.encode(), hashlib.sha256).hexdigest()


def test_tenant_signature_is_required():
    try:
        api.tenant("tenant-a", None)
        assert False, "missing signature must fail"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401


def test_wrong_tenant_signature_is_rejected():
    try:
        api.tenant("tenant-a", signature("tenant-b"))
        assert False, "wrong signature must fail"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401


def test_valid_tenant_signature_is_accepted():
    assert api.tenant("tenant-a", signature("tenant-a")) == "tenant-a"
