BEGIN;

ALTER TABLE evidence_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE verification_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE provenance_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE provenance_nodes FORCE ROW LEVEL SECURITY;
ALTER TABLE provenance_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE provenance_edges FORCE ROW LEVEL SECURITY;
ALTER TABLE ownership_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE ownership_records FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS evidence_tenant_isolation ON evidence_ledger;
CREATE POLICY evidence_tenant_isolation ON evidence_ledger USING (tenant_id::text = current_setting('tinyd.tenant_id', true)) WITH CHECK (tenant_id::text = current_setting('tinyd.tenant_id', true));
DROP POLICY IF EXISTS verification_tenant_isolation ON verification_evidence;
CREATE POLICY verification_tenant_isolation ON verification_evidence USING (tenant_id::text = current_setting('tinyd.tenant_id', true)) WITH CHECK (tenant_id::text = current_setting('tinyd.tenant_id', true));
DROP POLICY IF EXISTS provenance_nodes_tenant_isolation ON provenance_nodes;
CREATE POLICY provenance_nodes_tenant_isolation ON provenance_nodes USING (tenant_id::text = current_setting('tinyd.tenant_id', true)) WITH CHECK (tenant_id::text = current_setting('tinyd.tenant_id', true));
DROP POLICY IF EXISTS provenance_edges_tenant_isolation ON provenance_edges;
CREATE POLICY provenance_edges_tenant_isolation ON provenance_edges USING (tenant_id::text = current_setting('tinyd.tenant_id', true)) WITH CHECK (tenant_id::text = current_setting('tinyd.tenant_id', true));
DROP POLICY IF EXISTS ownership_tenant_isolation ON ownership_records;
CREATE POLICY ownership_tenant_isolation ON ownership_records USING (tenant_id::text = current_setting('tinyd.tenant_id', true)) WITH CHECK (tenant_id::text = current_setting('tinyd.tenant_id', true));

-- Policies are global definitions but remain immutable. Tenant context can be enforced at the service boundary.
DROP POLICY IF EXISTS policy_read ON policy_versions;
CREATE POLICY policy_read ON policy_versions FOR SELECT USING (true);
DROP POLICY IF EXISTS policy_insert ON policy_versions;
CREATE POLICY policy_insert ON policy_versions FOR INSERT WITH CHECK (true);

COMMIT;
