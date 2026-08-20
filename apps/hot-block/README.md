# Hot Block App

Hot Block is the execution cockpit for the TinyD deterministic runtime.

## UI

- Dashboard and runtime health
- Active execution graph
- Deterministic verification status
- Event stream / ledger view
- Replay controls
- Audit execution record

## Run

Serve this directory with any static HTTP server. `index.html` is the application entry point.

The UI is intentionally dependency-free so it can be embedded into the TinyD control plane or deployed as a static artifact.
