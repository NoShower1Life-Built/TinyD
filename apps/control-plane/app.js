const API_BASE = window.NEXORA_API_URL || "/";
const $ = (selector) => document.querySelector(selector);
const tokenInput = $("#tenantToken");
const connectButton = $("#connectBtn");
const runButton = $("#runBtn");
const replayButton = $("#replayBtn");
const refreshButton = $("#refreshBtn");
let accessToken = "";

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = String(value);
}

async function request(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
    ...(accessToken ? { Authorization: "Bearer " + accessToken } : {}),
  };
  const response = await fetch(
    new URL(path.replace(/^\\//, ""), new URL(API_BASE, window.location.href)),
    { ...options, headers: { "content-type": "application/json", ...headers } },
  );
  if (!response.ok) {
    let detail = "HTTP " + response.status;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function setConnected(connected, detail = "") {
  setText("#healthText", connected ? "Tenant connected" : "Disconnected");
  setText("#healthDetail", detail || (connected ? "authenticated runtime access" : "connect with a tenant token"));
  setText("#runtimeMode", connected ? "CONNECTED" : "AUTH REQUIRED");
  setText("#statusPill", connected ? "CONNECTED" : "LOCKED");
  runButton.disabled = !connected;
  replayButton.disabled = !connected;
  refreshButton.disabled = !connected;
}

function renderStatus(status) {
  setText("#activeExecutions", status.execution_count);
  setText("#eventCount", status.event_count);
  setText("#replayReady", status.replay_ready ? "READY" : "EMPTY");
  setText("#verification", status.verification.replaceAll("_", " "));
  setText("#runtimeMode", status.mode.toUpperCase());
  setText("#healthText", "Tenant connected");
  setText("#healthDetail", status.persistence + " · " + status.event_count + " tenant events");
  setText("#statusPill", "CONNECTED");
  setText("#statusValue", status.verification === "not_configured" ? "N/A" : status.verification);
  setText("#apiCheck", "PASS");
  setText("#engineCheck", "PASS");
  setText("#replayCheck", status.replay_ready ? "READY" : "EMPTY");
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = value == null ? "" : String(value);
  row.append(cell);
}

function renderEvents(events) {
  const rows = $("#eventRows");
  if (!rows) return;
  rows.replaceChildren();
  if (!events.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty-table";
    cell.textContent = "No tenant events recorded.";
    row.append(cell);
    rows.append(row);
    setText("#activityState", "No executions have been submitted.");
    setText("#activityStatus", "waiting");
    return;
  }
  for (const event of events) {
    const row = document.createElement("tr");
    appendCell(row, event.id, "mono");
    appendCell(row, event.type);
    appendCell(row, event.workflow || event.package_id || "—");
    appendCell(row, event.type === "workflow.replayed" ? "replayed" : "recorded");
    appendCell(row, event.timestamp);
    rows.append(row);
  }
  setText("#activityState", events.length + " tenant event" + (events.length === 1 ? "" : "s") + " loaded.");
  setText("#activityStatus", "connected");
}

async function refresh() {
  if (!accessToken) {
    setConnected(false);
    return;
  }
  try {
    const results = await Promise.all([request("v1/runtime/status"), request("v1/events")]);
    renderStatus(results[0]);
    renderEvents(results[1].events);
    setConnected(true, results[1].tenant_id + " · " + results[0].persistence);
  } catch (error) {
    setConnected(false, error.message);
    setText("#statusValue", "LOCKED");
    setText("#apiCheck", "AUTH ERROR");
    setText("#engineCheck", "UNKNOWN");
    setText("#replayCheck", "UNKNOWN");
  }
}

async function connectTenant() {
  const candidate = tokenInput.value.trim();
  if (!candidate) {
    setConnected(false, "Enter a tenant bearer token.");
    tokenInput.focus();
    return;
  }
  accessToken = candidate;
  connectButton.disabled = true;
  connectButton.textContent = "Connecting…";
  await refresh();
  connectButton.disabled = false;
  connectButton.textContent = accessToken && !runButton.disabled ? "Connected" : "Connect";
  if (runButton.disabled) accessToken = "";
}

async function runWorkflow() {
  const workflow = window.prompt("Workflow name", "nexora-check");
  if (!workflow) return;
  runButton.disabled = true;
  runButton.textContent = "Submitting…";
  try {
    await request("v1/executions", { method: "POST", body: JSON.stringify({ workflow, payload: {} }) });
    await refresh();
  } catch (error) {
    window.alert("Execution submission failed: " + error.message);
  } finally {
    runButton.textContent = "Run workflow";
    runButton.disabled = !accessToken;
  }
}

async function replayLatest() {
  replayButton.disabled = true;
  replayButton.textContent = "Replaying…";
  try {
    const result = await request("v1/events");
    const latest = [...result.events].reverse().find((event) => event.type === "workflow.requested");
    if (!latest) {
      window.alert("No workflow request is available for replay.");
      return;
    }
    await request("v1/replay", { method: "POST", body: JSON.stringify({ event_id: latest.id }) });
    await refresh();
  } catch (error) {
    window.alert("Replay failed: " + error.message);
  } finally {
    replayButton.textContent = "Replay latest";
    replayButton.disabled = !accessToken;
  }
}

connectButton?.addEventListener("click", connectTenant);
tokenInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") connectTenant();
});
runButton?.addEventListener("click", runWorkflow);
replayButton?.addEventListener("click", replayLatest);
refreshButton?.addEventListener("click", refresh);
document.querySelectorAll("nav a").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelectorAll("nav a").forEach((item) => item.classList.remove("active"));
    link.classList.add("active");
  });
});
setConnected(false);
