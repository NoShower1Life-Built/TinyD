# TinyD Agent Runtime Kernel

A concrete single-host agent execution kernel that composes four mechanisms:

1. **Tool executor and registry** — explicit callable registration and JSON input/output contract.
2. **HotBlock** — persistent operator-controlled execution enable/disable gate, checked immediately before every handler call.
3. **Bandit policy** — Thompson sampling over enabled tools, updated only from explicit bounded reward feedback.
4. **Artifact store** — durable SQLite execution records with a SHA-256 append chain, failure records, and verification.

## Runtime flow

`registered tools -> enabled-tool filter -> Thompson selection (or explicit tool) -> HotBlock check -> handler -> artifact commit -> external evaluation -> reward update`

A successful execution is not automatically treated as a successful task. The caller supplies a reward in [0, 1] after evaluating the actual outcome. Tool exceptions are recorded as failed artifacts; they do not silently poison the policy or automatically block a tool.

## Use

```python
from packages.agent_kernel.src import AgentRuntimeKernel

kernel = AgentRuntimeKernel("./var/tinyd-kernel.sqlite3", seed=17)
kernel.register_tool("lookup", lambda payload: {"value": payload["key"]})
result = kernel.run({"key": "status"})
if result["status"] == "succeeded":
    # Supply this only after evaluating the task outcome.
    kernel.reward(result["execution_id"], 1.0)
```

Block and re-enable a tool explicitly:

```python
kernel.hotblock.block("lookup", "operator disabled pending review")
kernel.hotblock.allow("lookup")
```

Inspect and verify artifacts:

```python
artifacts = kernel.store.list_artifacts(limit=100)
assert kernel.store.verify_artifact_chain()
```

## Install and test

Requires Python 3.11+. The kernel itself uses only the Python standard library.

```bash
python -m pytest tests/agent_kernel -q
```

## Operational boundaries

- SQLite WAL makes this a durable **single-host** kernel, not a multi-host distributed store.
- The current artifact chain detects modification/deletion/reordering relative to its retained head, but a privileged attacker who can rewrite the entire database can recompute it. Anchor digests externally for tamper evidence.
- The runtime does not sandbox Python callables. Untrusted tools must execute in a separate OS/container/microVM boundary.
- No automatic reward inference, automatic tool blocking, or autonomous permission escalation occurs.
- Do not pass credentials or sensitive payload fields unless the caller has configured appropriate redaction and storage controls.
- This module is additive. It does not replace TinyD's existing PostgreSQL event journal, workflow engine, tenant auth, or production execution path. The next integration step is a PostgreSQL-backed implementation of the same store contract and wiring through the existing authenticated API.
