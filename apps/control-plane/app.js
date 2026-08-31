const apiBase = document.querySelector('meta[name="tinyd-api-base"]')?.content?.replace(/\/$/, '') || '';
const tenantId = document.querySelector('meta[name="tinyd-tenant-id"]')?.content || '';
const runButton = document.querySelector('#runBtn');
const replayButton = document.querySelector('#replayBtn');
const tenantValue = document.querySelector('#tenantValue');
const connectionState = document.querySelector('#connectionState');
const connectionDetail = document.querySelector('#connectionDetail');
const runtimeState = document.querySelector('#runtimeState');

function setText(id, value) {
  const node = document.querySelector(`#${id}`);
  if (node) node.textContent = String(value);
}

function headers() {
  return { 'X-TinyD-Tenant-ID': tenantId };
}

async function get(path) {
  if (!apiBase || !tenantId) throw new Error('API base or tenant context is not configured');
  const response = await fetch(`${apiBase}${path}`, { headers: headers(), credentials: 'same-origin' });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function renderEvidence(rows) {
  const node = document.querySelector('#evidenceState');
  if (!node) return;
  if (!rows.length) {
    node.innerHTML = '<strong>No evidence in projection</strong><span>The tenant-scoped ledger contains no records.</span><code>PostgreSQL → API → Scoreboard</code>';
    return;
  }
  node.innerHTML = `<strong>${rows.length} evidence record${rows.length === 1 ? '' : 's'} loaded</strong><span>Latest canonical record: ${rows[0].event_id}</span><code>record ${rows[0].record_digest}</code>`;
}

function renderReplay(rows) {
  const node = document.querySelector('#replayState');
  if (!node) return;
  const latest = rows[0];
  if (!latest) {
    node.innerHTML = '<strong>No recorded verification</strong><span>No verification evidence exists for the selected tenant.</span><code>ReplayVerifier → verification evidence</code>';
    return;
  }
  node.innerHTML = `<strong>${latest.result}</strong><span>${latest.verifier_id} ${latest.verifier_version}</span><code>${latest.verification_digest}</code>`;
}

function renderAuthorization(rows) {
  const node = document.querySelector('#authorizationState');
  if (!node) return;
  const latest = rows[0];
  if (!latest) return;
  node.innerHTML = `<div><b>PolicyEngine</b><span>${latest.policy_id || 'unbound'}</span></div><div><b>Version</b><span>${latest.policy_version}</span></div><div><b>Digest</b><span>${latest.policy_digest}</span></div><div><b>Actor / capability</b><span>${latest.actor} / ${latest.capability}</span></div>`;
}

async function load() {
  if (!tenantId) {
    connectionState.textContent = 'Context required';
    connectionDetail.textContent = 'configure tenant identity';
    runtimeState.textContent = 'CONTEXT REQUIRED';
    return;
  }
  tenantValue.textContent = tenantId;
  try {
    const [summary, evidence, executions] = await Promise.all([
      get('/api/v1/assurance/summary'), get('/api/v1/evidence?limit=25'), get('/api/v1/executions?limit=25')
    ]);
    setText('metricExecutions', summary.execution_count);
    setText('metricExecutionsDetail', `${executions.length} returned from projection`);
    setText('metricEvidence', summary.evidence_count);
    setText('metricEvidenceDetail', `${summary.evidence_count} canonical records`);
    setText('metricPolicy', summary.policy_bound_count);
    setText('metricPolicyDetail', 'policy-bound evidence records');
    setText('metricArtifacts', summary.artifact_count);
    setText('metricArtifactsDetail', 'artifact-linked evidence records');
    setText('metricReplay', summary.verified_count);
    setText('metricReplayDetail', `${summary.failed_count} recorded verification failures`);
    setText('metricTenant', 'ENFORCED');
    setText('metricTenantDetail', 'tenant-scoped API + PostgreSQL RLS');
    renderEvidence(evidence);
    const execution = executions[0];
    if (execution) {
      const auth = await get(`/api/v1/authorization/${encodeURIComponent(execution.execution_id)}`);
      renderAuthorization(auth);
      const replay = await get(`/api/v1/replay/${encodeURIComponent(execution.execution_id)}`);
      renderReplay(replay.recorded_verifications || []);
    }
    connectionState.textContent = 'Connected';
    connectionDetail.textContent = 'authoritative API boundary';
    runtimeState.textContent = 'ASSURANCE CONNECTED';
  } catch (error) {
    connectionState.textContent = 'Unavailable';
    connectionDetail.textContent = error.message;
    runtimeState.textContent = 'API UNAVAILABLE';
  }
}

runButton?.addEventListener('click', () => {
  // Execution submission is intentionally disabled until the real kernel command API is present.
  runButton.textContent = 'Kernel command API required';
});

replayButton?.addEventListener('click', load);

document.querySelectorAll('nav a').forEach(link => link.addEventListener('click', () => {
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
  link.classList.add('active');
}));

load();
