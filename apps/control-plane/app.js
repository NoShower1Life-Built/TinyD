const API_BASE = window.NEXORA_API_URL || '/';

const $ = (selector) => document.querySelector(selector);
const runButton = $('#runBtn');
const replayButton = $('#replayBtn');
const refreshButton = $('#refreshBtn');

async function request(path, options = {}) {
  const response = await fetch(new URL(path.replace(/^\//, ''), new URL(API_BASE, window.location.href)), {
    headers: { 'content-type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value;
}

function renderStatus(status) {
  setText('#activeExecutions', status.execution_count);
  setText('#eventCount', status.event_count);
  setText('#replayReady', status.replay_ready ? 'READY' : 'EMPTY');
  setText('#verification', status.verification.replaceAll('_', ' '));
  setText('#runtimeMode', status.mode.toUpperCase());
  setText('#healthText', 'Runtime healthy');
  setText('#healthDetail', `${status.event_count} events loaded`);
  setText('#statusPill', 'CONNECTED');
  setText('#statusValue', status.verification === 'not_configured' ? 'N/A' : status.verification);
  setText('#apiCheck', 'PASS');
  setText('#engineCheck', 'PASS');
  setText('#replayCheck', status.replay_ready ? 'READY' : 'EMPTY');
}

function renderEvents(events) {
  const rows = $('#eventRows');
  if (!rows) return;
  if (!events.length) {
    rows.innerHTML = '<tr><td colspan="6" class="empty-table">No runtime events recorded.</td></tr>';
    setText('#activityState', 'No executions have been submitted.');
    setText('#activityStatus', 'waiting');
    return;
  }
  rows.innerHTML = events.map((event) => `
    <tr>
      <td class="mono">${event.id}</td>
      <td>${event.type}</td>
      <td>${event.workflow}</td>
      <td><span class="tag live">accepted</span></td>
      <td>${event.timestamp}</td>
      <td>→</td>
    </tr>`).join('');
  setText('#activityState', `${events.length} runtime event${events.length === 1 ? '' : 's'} loaded.`);
  setText('#activityStatus', 'connected');
}

async function refresh() {
  try {
    const [status, eventResult] = await Promise.all([
      request('v1/runtime/status'),
      request('v1/events'),
    ]);
    renderStatus(status);
    renderEvents(eventResult.events);
  } catch (error) {
    setText('#healthText', 'Runtime unavailable');
    setText('#healthDetail', error.message);
    setText('#runtimeMode', 'OFFLINE');
    setText('#statusPill', 'OFFLINE');
    setText('#statusValue', 'OFFLINE');
    setText('#apiCheck', 'FAIL');
    setText('#engineCheck', 'UNKNOWN');
    setText('#replayCheck', 'UNKNOWN');
  }
}

async function runWorkflow() {
  const workflow = window.prompt('Workflow name', 'nexora-check');
  if (!workflow) return;
  runButton.disabled = true;
  runButton.textContent = 'Submitting…';
  try {
    await request('v1/executions', {
      method: 'POST',
      body: JSON.stringify({ workflow, payload: {} }),
    });
    await refresh();
    runButton.textContent = 'Submitted';
  } catch (error) {
    runButton.textContent = 'Failed';
    window.alert(`Execution submission failed: ${error.message}`);
  } finally {
    setTimeout(() => { runButton.textContent = 'Run workflow'; runButton.disabled = false; }, 1000);
  }
}

async function replayLatest() {
  try {
    const result = await request('v1/events');
    const latest = result.events.at(-1);
    if (!latest) {
      window.alert('No runtime event is available for replay.');
      return;
    }
    replayButton.disabled = true;
    replayButton.textContent = 'Replaying…';
    await request('v1/replay', {
      method: 'POST',
      body: JSON.stringify({ event_id: latest.id }),
    });
    await refresh();
    replayButton.textContent = 'Replay complete';
  } catch (error) {
    replayButton.textContent = 'Replay failed';
    window.alert(`Replay failed: ${error.message}`);
  } finally {
    setTimeout(() => { replayButton.textContent = 'Replay latest'; replayButton.disabled = false; }, 1000);
  }
}

runButton?.addEventListener('click', runWorkflow);
replayButton?.addEventListener('click', replayLatest);
refreshButton?.addEventListener('click', refresh);
document.querySelectorAll('nav a').forEach((link) => link.addEventListener('click', () => {
  document.querySelectorAll('nav a').forEach((a) => a.classList.remove('active'));
  link.classList.add('active');
}));

refresh();
