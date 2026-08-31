BEGIN;

CREATE OR REPLACE FUNCTION tinyd_reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'immutable assurance record: % is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS evidence_ledger_immutable ON evidence_ledger;
CREATE TRIGGER evidence_ledger_immutable
BEFORE UPDATE OR DELETE ON evidence_ledger
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS policy_versions_immutable ON policy_versions;
CREATE TRIGGER policy_versions_immutable
BEFORE UPDATE OR DELETE ON policy_versions
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS verification_evidence_immutable ON verification_evidence;
CREATE TRIGGER verification_evidence_immutable
BEFORE UPDATE OR DELETE ON verification_evidence
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS provenance_nodes_immutable ON provenance_nodes;
CREATE TRIGGER provenance_nodes_immutable
BEFORE UPDATE OR DELETE ON provenance_nodes
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS provenance_edges_immutable ON provenance_edges;
CREATE TRIGGER provenance_edges_immutable
BEFORE UPDATE OR DELETE ON provenance_edges
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS ownership_records_immutable ON ownership_records;
CREATE TRIGGER ownership_records_immutable
BEFORE UPDATE OR DELETE ON ownership_records
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

ALTER TABLE ownership_records
    DROP CONSTRAINT IF EXISTS ownership_records_evidence_fk;
ALTER TABLE ownership_records
    ADD CONSTRAINT ownership_records_evidence_fk
    FOREIGN KEY (tenant_id, evidence_digest)
    REFERENCES evidence_ledger (tenant_id, record_digest);

ALTER TABLE verification_evidence
    DROP CONSTRAINT IF EXISTS verification_evidence_digest_format;
ALTER TABLE verification_evidence
    ADD CONSTRAINT verification_evidence_digest_format
    CHECK (subject_digest ~ '^[0-9a-f]{64}$' AND evidence_digest ~ '^[0-9a-f]{64}$' AND verification_digest ~ '^[0-9a-f]{64}$');

ALTER TABLE evidence_ledger
    DROP CONSTRAINT IF EXISTS evidence_ledger_digest_format;
ALTER TABLE evidence_ledger
    ADD CONSTRAINT evidence_ledger_digest_format
    CHECK (
        event_digest ~ '^[0-9a-f]{64}$' AND record_digest ~ '^[0-9a-f]{64}$' AND
        (previous_record_digest IS NULL OR previous_record_digest ~ '^[0-9a-f]{64}$') AND
        (policy_digest IS NULL OR policy_digest ~ '^[0-9a-f]{64}$') AND
        (code_digest IS NULL OR code_digest ~ '^[0-9a-f]{64}$') AND
        (artifact_digest IS NULL OR artifact_digest ~ '^[0-9a-f]{64}$') AND
        (input_digest IS NULL OR input_digest ~ '^[0-9a-f]{64}$') AND
        (output_digest IS NULL OR output_digest ~ '^[0-9a-f]{64}$')
    );

COMMIT;
