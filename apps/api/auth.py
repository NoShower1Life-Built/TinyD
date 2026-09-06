from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Tenant:
    id: str
    scopes: frozenset[str]


def _token_map() -> dict[str, dict]:
    raw = os.environ.get("TINYD_TENANT_TOKENS", "")
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        value = {}
    return value if isinstance(value, dict) else {}


def require_tenant(authorization: str | None = Header(default=None)) -> Tenant:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="invalid tenant credentials")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    for configured_hash, identity in _token_map().items():
        if not isinstance(configured_hash, str) or not isinstance(identity, dict):
            continue
        if hmac.compare_digest(configured_hash, token_hash):
            tenant_id = identity.get("tenant_id")
            scopes = identity.get("scopes", [])
            if not isinstance(tenant_id, str) or not tenant_id.strip() or not isinstance(scopes, list):
                break
            return Tenant(tenant_id.strip(), frozenset(str(scope) for scope in scopes))
    raise HTTPException(status_code=401, detail="invalid tenant credentials")


def require_scope(tenant: Tenant, scope: str) -> None:
    if scope not in tenant.scopes:
        raise HTTPException(status_code=403, detail=f"missing scope: {scope}")
