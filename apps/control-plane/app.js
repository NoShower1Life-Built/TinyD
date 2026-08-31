const apiBase = document.querySelector('meta[name="tinyd-api-base"]')?.content?.replace(/\/$/, '') || window.location.origin;
const tenantId = document.querySelector('meta[name="tinyd-tenant-id"]')?.content || '';
const tenantSignature = document.querySelector('meta[name="tinyd-tenant-signature"]')?.content || '';
const tenantSource = document.querySelector('meta[name="tinyd-tenant-source"]')?.content || 'unknown';
const runButton = document.querySelector('#runBtn');
const replayButton = document.querySelector('#replayBtn');
const tenantValue = document.querySelector('#tenantValue');
const connectionState = document.querySelector('#connectionState');
const connectionDetail = document.querySelector('#connectionDetail');
const runtimeState = document.querySelector('#runtimeState');

function setText(id, value) { const node = document.querySelector(`#${id}`); if (node) node.textContent = String(value ?? ''); }
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function append(node, tag, value) { const child = document.createElement(tag); child.textContent = String(value ?? ''); node.appendChild(child); return child; }
function headers() { return { 'X-TinyD-Tenant-ID': tenantId, 'X-TinyD-Tenant-Signature': tenantSignature }; }
async function get(path) {
  if (!apiBase || !tenantId || !tenantSignature) throw new Error('authenticated tenant context is not configured');
  const response = await fetch(`${apiBase}${path}`, { headers: headers(), credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}
function renderEvidence(rows) {
  const node = document.querySelector('#evidenceState'); if (!node) return;
  clear(node);
  if (!rows.length) { append(node, 'strong', 'No evidence in projection'); append(node, 'span', 'The tenant-scoped ledger contains no records.'); append(node, 'code', 'PostgreSQL → API → Scoreboard'); return; }
  append(node, 'strong', `${rows.length} evidence record${rows.length === 1 ? '' : 's'} loaded`);
  append(node, 'span', `Latest canonical record: ${rows[0].event_id}`);
  append(node, 'code', `record ${rows[0].record_digest}`);
}
function renderReplay(rows) {
  const node = document.querySelector('#replayState'); if (!node) return;
  clear(node);
  const latest = rows[0];
  if (!latest) { append(node, 'strong', 'No recorded verification'); append(node, 'span', 'No verification evidence exists for the selected tenant.'); append(node, 'code', 'ReplayVerifier → verification evidence'); return; }
  append(node, 'strong', `Recorded verification: ${latest.result}`);
  append(node, 'span', `${latest.verifier_id || 'unknown verifier'} ${latest.verifier_version || ''}`.trim());
  append(node, 'code', latest.verification_digest);
  append(node, 'span', 'Independent replay execution: NOT ESTABLISHED by this record');
}
function renderAuthorization(rows) {
  const node = document.querySelector('#authorizationState'); if (!node || !rows.length) return;
  clear(node); const latest = rows[0];
  [['PolicyEngine', latest.policy_id || 'unbound'], ['Version', latest.policy_version], ['Digest', latest.policy_digest], ['Actor / capability', `${latest.actor || ''} / ${latest.capability || ''}`]].forEach(([label, value]) => { const row = document.createElement('div'); append(row, 'b', label); append(row, 'span', value); node.appendChild(row); });
}
function renderExecutions(rows) {
  const node = document.querySelector('#executionState'); if (!node) return;
  clear(node);
  if (!rows.length) { append(node, 'strong', 'No executions in projection'); append(node, 'span', 'No tenant-scoped execution records were returned.'); return; }
  append(node, 'strong', `${rows.length} execution record${rows.length === 1 ? '' : 's'} loaded`);
  append(node, 'span', `Latest execution: ${rows[0].execution_id}`);
}
function renderAssurance(projection) {
  const status = projection?.derived_status || 'UNPROVEN';
  setText('assuranceStatus', status);
  setText('assuranceAuthority', projection?.authoritative_source || 'Authoritative Scoreboard projection');
  setText('assuranceRequirement', projection?.requirement_id || 'No authoritative requirement exposed');
  setText('assuranceEvidence', projection?.evidence_refs?.length ? `${projection.evidence_refs.length} authoritative evidence reference(s)` : 'No authoritative evidence');
  setText('assuranceReplay', projection?.replay_verification_ref ? `Recorded verification: ${projection.replay_verification_ref}; independent replay not established by this projection` : 'Independent replay not established');
}
async function load() {
  if (!tenantId || !tenantSignature) { connectionState.textContent = 'Context required'; connectionDetail.textContent = 'server-provided tenant assertion required'; runtimeState.textContent = 'CONTEXT REQUIRED'; return; }
  tenantValue.textContent = tenantId; setText('assuranceAuthority', `Authoritative Scoreboard projection · tenant source: ${tenantSource}`);
  try {
    const [summary, projection, evidence, executions] = await Promise.all([get('/api/v1/assurance/summary'), get('/api/v1/assurance/projection'), get('/api/v1/evidence?limit=25'), get('/api/v1/executions?limit=25')]);
    setText('metricExecutions', summary.execution_count); setText('metricExecutionsDetail', `${executions.length} returned from projection`);
    setText('metricEvidence', summary.evidence_count); setText('metricEvidenceDetail', `${summary.evidence_count} canonical records`);
    setText('metricPolicy', summary.policy_bound_count); setText('metricPolicyDetail', 'policy-bound evidence records');
    setText('metricArtifacts', summary.artifact_count); setText('metricArtifactsDetail', 'artifact-linked evidence records');
    setText('metricReplay', summary.verified_count); setText('metricReplayDetail', `${summary.failed_count} recorded verification failures`);
    setText('metricTenant', 'ENFORCED'); setText('metricTenantDetail', 'tenant-scoped API + PostgreSQL RLS');
    renderEvidence(evidence); renderExecutions(executions); renderAssurance(projection);
    const execution = executions[0];
    if (execution) { renderAuthorization(await get(`/api/v1/authorization/${encodeURIComponent(execution.execution_id)}`)); renderReplay((await get(`/api/v1/replay/${encodeURIComponent(execution.execution_id)}`)).recorded_verifications || []); }
    connectionState.textContent = 'Connected'; connectionDetail.textContent = 'authoritative API boundary'; runtimeState.textContent = 'ASSURANCE CONNECTED';
  } catch (error) { connectionState.textContent = 'Unavailable'; connectionDetail.textContent = error instanceof Error ? error.message : 'request failed'; runtimeState.textContent = 'API UNAVAILABLE'; }
}
runButton?.addEventListener('click', () => { runButton.textContent = 'Kernel command API required'; });
replayButton?.addEventListener('click', load);
document.querySelectorAll('nav a').forEach(link => link.addEventListener('click', () => { document.querySelectorAll('nav a').forEach(a => a.classList.remove('active')); link.classList.add('active'); }));
load();
