from __future__ import annotations
import hashlib, hmac, os
from typing import Any, Mapping
from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
import psycopg
from psycopg.rows import dict_row

_AUTH_KEY = os.getenv("TINYD_TENANT_SIGNING_KEY")
if not _AUTH_KEY or len(_AUTH_KEY.encode()) < 32:
    raise RuntimeError("TINYD_TENANT_SIGNING_KEY must contain at least 32 bytes; tenant authentication is fail-closed")
app = FastAPI(title="TinyD API", version="1.1", docs_url=None if os.getenv("TINYD_DISABLE_API_DOCS", "true").lower() == "true" else "/docs", redoc_url=None, openapi_url=None if os.getenv("TINYD_DISABLE_API_DOCS", "true").lower() == "true" else "/openapi.json")
_allowed_origins = [x.strip() for x in os.getenv("TINYD_CORS_ORIGINS", "").split(",") if x.strip()]
if _allowed_origins:
    app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["X-TinyD-Tenant-ID", "X-TinyD-Tenant-Signature"])

@app.middleware("http")
async def security_headers(request, call_next):
    response: Response = await call_next(request)
    response.headers.update({"X-Content-Type-Options":"nosniff", "Cache-Control":"no-store", "Referrer-Policy":"no-referrer", "X-Frame-Options":"DENY"})
    return response

def tenant(value: str | None, signature: str | None) -> str:
    if not value or len(value) > 128 or value.strip() != value or not signature or len(signature) != 64:
        raise HTTPException(401, "tenant authentication required")
    expected = hmac.new(_AUTH_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected): raise HTTPException(401, "tenant authentication required")
    return value

def db():
    url = os.getenv("DATABASE_URL")
    if not url: raise HTTPException(503, "database unavailable")
    try: return psycopg.connect(url, row_factory=dict_row)
    except psycopg.Error as exc: raise HTTPException(503, "database unavailable") from exc

def query(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('tinyd.tenant_id', %s, true)", (params[0],))
                cur.execute(sql, params)
                return list(cur.fetchall())
    except HTTPException: raise
    except psycopg.Error as exc: raise HTTPException(503, "projection unavailable") from exc

def auth(x_tinyd_tenant_id: str | None, x_tinyd_tenant_signature: str | None) -> str: return tenant(x_tinyd_tenant_id, x_tinyd_tenant_signature)

class AssuranceProjectionPartial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    projection_version: str = "1-partial"
    tenant_id: str
    derived_status: str
    authoritative_source: str
    requirement_id: str | None
    implementation_ref: str | None
    test_ref: str | None
    execution_ref: str | None
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]
    replay_verification_ref: str | None
    trust_root_ref: str | None
    unavailable_dimensions: tuple[str, ...]
    assurance_assertion: str


def build_partial_projection(tenant_id: str, executions: list[Mapping[str, Any]], evidence: list[Mapping[str, Any]], replay: list[Mapping[str, Any]]) -> AssuranceProjectionPartial:
    execution_ref = str(executions[0]["execution_id"]) if executions else None
    evidence_refs = tuple(str(row["evidence_id"]) for row in evidence if row.get("evidence_id") is not None)
    provenance_refs = tuple(sorted({str(row["provenance_id"]) for row in evidence if row.get("provenance_id") is not None}))
    verification_refs = tuple(str(row["verification_id"]) for row in replay if row.get("verification_id") is not None)
    replay_ref = verification_refs[0] if verification_refs else None
    unavailable = ("requirement", "implementation", "test_certification", "trust_root")
    return AssuranceProjectionPartial(
        tenant_id=tenant_id,
        derived_status="UNPROVEN",
        authoritative_source="TinyD API authoritative projections",
        requirement_id=None,
        implementation_ref=None,
        test_ref=None,
        execution_ref=execution_ref,
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        verification_refs=verification_refs,
        replay_verification_ref=replay_ref,
        trust_root_ref=None,
        unavailable_dimensions=unavailable,
        assurance_assertion="UNPROVEN: authoritative requirement, implementation, test certification, and trust-root records are not exposed by the existing API source",
    )

@app.get("/health")
def health(): return {"status":"ok", "service":"tinyd-api"}

@app.get("/api/v1/assurance/summary")
def assurance_summary(x_tinyd_tenant_id: str | None = Header(default=None), x_tinyd_tenant_signature: str | None = Header(default=None)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature)
    rows=query("SELECT count(*)::bigint AS evidence_count, count(DISTINCT execution_id)::bigint AS execution_count, count(*) FILTER (WHERE artifact_digest IS NOT NULL)::bigint AS artifact_count, count(*) FILTER (WHERE policy_version IS NOT NULL)::bigint AS policy_bound_count FROM evidence_ledger WHERE tenant_id=%s",(t,))
    verified=query("SELECT count(*)::bigint AS verified_count FROM verification_evidence WHERE tenant_id=%s AND result='VERIFIED'",(t,)); failed=query("SELECT count(*)::bigint AS failed_count FROM verification_evidence WHERE tenant_id=%s AND result='FAILED'",(t,)); return {**rows[0],**verified[0],**failed[0]}

@app.get("/api/v1/assurance/projection", response_model=AssuranceProjectionPartial)
def assurance_projection(x_tinyd_tenant_id: str | None = Header(default=None), x_tinyd_tenant_signature: str | None = Header(default=None)):
    """Read-only partial Scoreboard projection from existing authoritative API records."""
    t = auth(x_tinyd_tenant_id, x_tinyd_tenant_signature)
    executions_rows = query("SELECT execution_id,min(created_at) AS first_seen,max(created_at) AS last_seen,count(*)::bigint AS event_count,max(event_type) AS last_event_type FROM evidence_ledger WHERE tenant_id=%s GROUP BY execution_id ORDER BY last_seen DESC LIMIT 1", (t,))
    evidence_rows = query("SELECT evidence_id,provenance_id FROM evidence_ledger WHERE tenant_id=%s ORDER BY sequence DESC LIMIT 100", (t,))
    replay_rows = query("SELECT v.verification_id FROM verification_evidence v JOIN evidence_ledger e ON e.tenant_id=v.tenant_id AND e.record_digest=v.evidence_digest WHERE v.tenant_id=%s ORDER BY v.created_at DESC LIMIT 100", (t,))
    return build_partial_projection(t, executions_rows, evidence_rows, replay_rows)

@app.get("/api/v1/executions")
def executions(x_tinyd_tenant_id: str | None=Header(default=None), x_tinyd_tenant_signature: str | None=Header(default=None), limit:int=Query(50,ge=1,le=200)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); return query("SELECT execution_id,min(created_at) AS first_seen,max(created_at) AS last_seen,count(*)::bigint AS event_count,max(event_type) AS last_event_type FROM evidence_ledger WHERE tenant_id=%s GROUP BY execution_id ORDER BY last_seen DESC LIMIT %s",(t,limit))

_EVIDENCE_COLUMNS="evidence_id, sequence, event_id, event_type, execution_id, actor, capability, operation, policy_id, policy_version, policy_digest, code_digest, artifact_digest, input_digest, output_digest, provenance_id, idempotency_key, event_digest, previous_record_digest, record_digest, created_at"

@app.get("/api/v1/evidence")
def evidence(x_tinyd_tenant_id:str|None=Header(default=None), x_tinyd_tenant_signature:str|None=Header(default=None), execution_id:str|None=None, limit:int=Query(100,ge=1,le=500)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); sql=f"SELECT {_EVIDENCE_COLUMNS} FROM evidence_ledger WHERE tenant_id=%s"; params=[t]
    if execution_id: sql += " AND execution_id=%s"; params.append(execution_id)
    sql += " ORDER BY sequence DESC LIMIT %s"; params.append(limit); return query(sql,tuple(params))

@app.get("/api/v1/evidence/{evidence_id}")
def evidence_by_id(evidence_id:str,x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); rows=query(f"SELECT {_EVIDENCE_COLUMNS} FROM evidence_ledger WHERE tenant_id=%s AND evidence_id=%s",(t,evidence_id))
    if not rows: raise HTTPException(404,"evidence not found")
    return rows[0]

@app.get("/api/v1/provenance/{subject_id}")
def provenance(subject_id:str,x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); nodes=query("SELECT node_id,node_type,subject_digest,created_at FROM provenance_nodes WHERE tenant_id=%s AND node_id=%s",(t,subject_id))
    if not nodes: raise HTTPException(404,"provenance subject not found")
    edges=query("SELECT source_id,relationship,target_id FROM provenance_edges WHERE tenant_id=%s AND (source_id=%s OR target_id=%s)",(t,subject_id,subject_id)); return {"subject":nodes[0],"edges":edges}

@app.get("/api/v1/authorization/{execution_id}")
def authorization(execution_id:str,x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); return query("SELECT DISTINCT policy_id,policy_version,policy_digest,event_id,actor,capability,operation,created_at FROM evidence_ledger WHERE tenant_id=%s AND execution_id=%s AND policy_version IS NOT NULL ORDER BY created_at DESC",(t,execution_id))

@app.get("/api/v1/artifacts/{digest}")
def artifact(digest:str,x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); digest=digest.lower()
    if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest): raise HTTPException(400,"invalid SHA-256 digest")
    evidence=query("SELECT evidence_id,execution_id,artifact_digest,code_digest,policy_version,created_at FROM evidence_ledger WHERE tenant_id=%s AND artifact_digest=%s ORDER BY created_at DESC",(t,digest))
    if not evidence: raise HTTPException(404,"artifact evidence not found")
    return {"artifact_digest":digest,"evidence":evidence}

@app.get("/api/v1/replay/{execution_id}")
def replay(execution_id:str,x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature)
    rows=query("SELECT v.verification_id,v.subject_digest,v.result,v.verifier_id,v.verifier_version,v.verification_digest,v.reason,v.created_at FROM verification_evidence v JOIN evidence_ledger e ON e.tenant_id=v.tenant_id AND e.record_digest=v.evidence_digest WHERE v.tenant_id=%s AND e.execution_id=%s ORDER BY v.created_at DESC",(t,execution_id))
    return {"execution_id":execution_id,"recorded_verifications":rows,"replay_execution":False}

@app.get("/api/v1/policies")
def policies(x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None),limit:int=Query(100,ge=1,le=500)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); return query("SELECT policy_id,version,policy_digest,created_at FROM policy_versions WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s",(t,limit))

@app.get("/api/v1/audit")
def audit(x_tinyd_tenant_id:str|None=Header(default=None),x_tinyd_tenant_signature:str|None=Header(default=None),limit:int=Query(100,ge=1,le=500)):
    t=auth(x_tinyd_tenant_id,x_tinyd_tenant_signature); return query("SELECT sequence,evidence_id,event_id,event_type,execution_id,actor,operation,policy_version,artifact_digest,event_digest,previous_record_digest,record_digest,created_at FROM evidence_ledger WHERE tenant_id=%s ORDER BY sequence DESC LIMIT %s",(t,limit))
