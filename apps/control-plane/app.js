const apiBase = document.querySelector('meta[name="tinyd-api-base"]')?.content?.replace(/\/$/, '') || '';
const tenantId = document.querySelector('meta[name="tinyd-tenant-id"]')?.content || '';
const tenantSignature = document.querySelector('meta[name="tinyd-tenant-signature"]')?.content || '';
const runButton = document.querySelector('#runBtn');
const replayButton = document.querySelector('#replayBtn');
const tenantValue = document.querySelector('#tenantValue');
const connectionState = document.querySelector('#connectionState');
const connectionDetail = document.querySelector('#connectionDetail');
const runtimeState = document.querySelector('#runtimeState');

function setText(id, value) { const node = document.querySelector(`#${id}`); if (node) node.textContent = String(value); }
function headers() { return { 'X-TinyD-Tenant-ID': tenantId, 'X-TinyD-Tenant-Signature': tenantSignature }; }
async function get(path) {
  if (!apiBase || !tenantId || !tenantSignature) throw new Error('authenticated tenant context is not configured');
  const response = await fetch(`${apiBase}${path}`, { headers: headers(), credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}
function renderEvidence(rows) {
  const node = document.querySelector('#evidenceState'); if (!node) return;
  if (!rows.length) { node.innerHTML = '<strong>No evidence in projection</strong><span>The tenant-scoped ledger contains no records.</span><code>PostgreSQL → API → Scoreboard</code>'; return; }
  node.innerHTML = `<strong>${rows.length} evidence record${rows.length === 1 ? '' : 's'} loaded</strong><span>Latest canonical record: ${String(rows[0].event_id)}</span><code>record ${String(rows[0].record_digest)}</code>`;
}
function renderReplay(rows) {
  const node = document.querySelector('#replayState'); if (!node) return;
  const latest = rows[0];
  if (!latest) { node.innerHTML = '<strong>No recorded verification</strong><span>No verification evidence exists for the selected tenant.</span><code>ReplayVerifier → verification evidence</code>'; return; }
  node.innerHTML = `<strong>${String(latest.result)}</strong><span>${String(latest.verifier_id)} ${String(latest.verifier_version)}</span><code>${String(latest.verification_digest)}</code>`;
}
function renderAuthorization(rows) {
  const node = document.querySelector('#authorizationState'); if (!node || !rows.length) return;
  const latest = rows[0];
  node.innerHTML = `<div><b>PolicyEngine</b><span>${String(latest.policy_id || 'unbound')}</span></div><div><b>Version</b><span>${String(latest.policy_version)}</span></div><div><b>Digest</b><span>${String(latest.policy_digest)}</span></div><div><b>Actor / capability</b><span>${String(latest.actor)} / ${String(latest.capability)}</span></div>`;
}
async function load() {
  if (!tenantId || !tenantSignature) { connectionState.textContent = 'Context required'; connectionDetail.textContent = 'server-provided tenant assertion required'; runtimeState.textContent = 'CONTEXT REQUIRED'; return; }
  tenantValue.textContent = tenantId;
  try {
    const [summary, evidence, executions] = await Promise.all([get('/api/v1/assurance/summary'), get('/api/v1/evidence?limit=25'), get('/api/v1/executions?limit=25')]);
    setText('metricExecutions', summary.execution_count); setText('metricExecutionsDetail', `${executions.length} returned from projection`);
    setText('metricEvidence', summary.evidence_count); setText('metricEvidenceDetail', `${summary.evidence_count} canonical records`);
    setText('metricPolicy', summary.policy_bound_count); setText('metricPolicyDetail', 'policy-bound evidence records');
    setText('metricArtifacts', summary.artifact_count); setText('metricArtifactsDetail', 'artifact-linked evidence records');
    setText('metricReplay', summary.verified_count); setText('metricReplayDetail', `${summary.failed_count} recorded verification failures`);
    setText('metricTenant', 'ENFORCED'); setText('metricTenantDetail', 'tenant-scoped API + PostgreSQL RLS'); renderEvidence(evidence);
    const execution = executions[0];
    if (execution) { renderAuthorization(await get(`/api/v1/authorization/${encodeURIComponent(execution.execution_id)}`)); renderReplay((await get(`/api/v1/replay/${encodeURIComponent(execution.execution_id)}`)).recorded_verifications || []); }
    connectionState.textContent = 'Connected'; connectionDetail.textContent = 'authoritative API boundary'; runtimeState.textContent = 'ASSURANCE CONNECTED';
  } catch (error) { connectionState.textContent = 'Unavailable'; connectionDetail.textContent = error instanceof Error ? error.message : 'request failed'; runtimeState.textContent = 'API UNAVAILABLE'; }
}
runButton?.addEventListener('click', () => { runButton.textContent = 'Kernel command API required'; });
replayButton?.addEventListener('click', load);
document.querySelectorAll('nav a').forEach(link => link.addEventListener('click', () => { document.querySelectorAll('nav a').forEach(a => a.classList.remove('active')); link.classList.add('active'); }));
load();
