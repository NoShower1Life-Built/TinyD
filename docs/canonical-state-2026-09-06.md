# TinyD Canonical State — 2026-09-06

## Role
TinyD is the execution/runtime kernel for the Nexus AI platform: an event-sourced, deterministic orchestration runtime for agents, tasks, workflows, and replayable execution.

## Canonical architecture
- FastAPI control plane
- Deterministic event/ledger model
- Kafka-oriented event transport and worker execution
- Redis/Postgres persistence components
- Replayable execution and idempotency boundaries
- Next.js/React control-plane UI integration
- Docker/Kubernetes/Terraform/Helm deployment path
- CI security and dependency gates

## Correctness requirements
1. Deterministic execution and stable event identity.
2. Idempotent execution and replay safety.
3. Tenant isolation and boundary enforcement.
4. Durable ledger/provenance before asynchronous publication.
5. Observable correlation across API, ledger, broker, worker, and replay paths.
6. Verification gates before production claims.

## Current GitHub state
The repository already contains the runtime scaffold, tests, deployment files, SBOM area, and CI/security structure. The latest integration commit is `9cdc0bdd5bdbbeebee5ea37e1e3d73039cddf041`, integrating the Nexora control plane with TinyD. The latest dependency/source security gate commit is `ec03efa053e78aef2506ced6629308a219a1b0a9`.

## Remaining engineering work
- Versioned event contracts/schema registry
- Backpressure/load shedding
- Replay throttling and replay controller/DLQ replay controller
- Snapshot/parity storage
- Strong Kafka consumer-group semantics
- Distributed Redis sharding where required
- OIDC/SAML and hardened tenant isolation
- SIEM integrations
- Formal verification layer (TLA+/SMT/Lean/VCIR) where justified
- Full repository build/test/lint/security/integration/browser-independent render gates

## Export rule
This document is a state record, not a claim that every historical chat artifact is physically present in the repository. Only artifacts actually committed to GitHub are considered exported.