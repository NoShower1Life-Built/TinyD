BEGIN;

CREATE TABLE IF NOT EXISTS evidence_ledger (
    tenant_id TEXT NOT NULL, sequence BIGINT NOT NULL, evidence_id TEXT NOT NULL, event_id TEXT NOT NULL,
    event_type TEXT NOT NULL, execution_id TEXT NOT NULL, actor TEXT NOT NULL, capability TEXT NOT NULL,
    operation TEXT NOT NULL, policy_id TEXT, policy_version TEXT, policy_digest CHAR(64), code_digest CHAR(64),
    artifact_digest CHAR(64), input_digest CHAR(64), output_digest CHAR(64), provenance_id TEXT,
    idempotency_key TEXT NOT NULL, event_digest CHAR(64) NOT NULL, previous_record_digest CHAR(64),
    record_digest CHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, sequence), UNIQUE (tenant_id, evidence_id), UNIQUE (tenant_id, idempotency_key), UNIQUE (tenant_id, event_id), UNIQUE (tenant_id, record_digest)
);
CREATE TABLE IF NOT EXISTS policy_versions (
    policy_id TEXT NOT NULL, version TEXT NOT NULL, policy_digest CHAR(64) NOT NULL, policy_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (policy_id, version), UNIQUE (policy_id, policy_digest)
);
CREATE TABLE IF NOT EXISTS verification_evidence (
    verification_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, subject_digest CHAR(64) NOT NULL,
    evidence_digest CHAR(64) NOT NULL, verifier_id TEXT NOT NULL, verifier_version TEXT NOT NULL, policy_version TEXT,
    trust_root TEXT, result TEXT NOT NULL CHECK (result IN ('VERIFIED','FAILED')), reason TEXT NOT NULL,
    verification_digest CHAR(64) NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS provenance_nodes (
    node_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, node_type TEXT NOT NULL, subject_digest CHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS provenance_edges (
    source_id TEXT NOT NULL, relationship TEXT NOT NULL, target_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (source_id, relationship, target_id),
    FOREIGN KEY (source_id) REFERENCES provenance_nodes(node_id), FOREIGN KEY (target_id) REFERENCES provenance_nodes(node_id)
);
CREATE TABLE IF NOT EXISTS ownership_records (
    tenant_id TEXT NOT NULL, subject_id TEXT NOT NULL, relationship TEXT NOT NULL, target_id TEXT NOT NULL,
    evidence_digest CHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, subject_id, relationship, target_id)
);
CREATE TABLE IF NOT EXISTS trust_keys (
    signer_id TEXT NOT NULL, key_version TEXT NOT NULL, algorithm TEXT NOT NULL, public_key_b64 TEXT NOT NULL,
    revoked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (signer_id, key_version)
);

ALTER TABLE verification_evidence DROP CONSTRAINT IF EXISTS verification_evidence_subject_fk;
ALTER TABLE verification_evidence ADD CONSTRAINT verification_evidence_subject_fk
    FOREIGN KEY (tenant_id, evidence_digest) REFERENCES evidence_ledger (tenant_id, record_digest);

COMMIT;
