BEGIN;

CREATE OR REPLACE FUNCTION tinyd_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'TinyD evidence/policy records are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS evidence_ledger_no_update ON evidence_ledger;
CREATE TRIGGER evidence_ledger_no_update BEFORE UPDATE OR DELETE ON evidence_ledger
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS policy_versions_no_update ON policy_versions;
CREATE TRIGGER policy_versions_no_update BEFORE UPDATE OR DELETE ON policy_versions
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

DROP TRIGGER IF EXISTS verification_evidence_no_update ON verification_evidence;
CREATE TRIGGER verification_evidence_no_update BEFORE UPDATE OR DELETE ON verification_evidence
FOR EACH ROW EXECUTE FUNCTION tinyd_reject_mutation();

COMMIT;
