# TinyD Production Architecture — Nexora Runtime

## Authority and product boundary

Nexus AI is the customer-facing enterprise SaaS platform. TinyD is its governed
execution runtime. The dashboard and API gateway submit and observe work; they
do not become a second execution authority.

TinyD's authoritative state is its append-only PostgreSQL event journal.
Derived task tables, caches, WebSocket projections, analytics, and message
streams are rebuildable projections and must never supersede journal history.

## Runtime path

`authenticated request`
→ tenant and scope authorization
→ immutable, versioned execution request
→ canonical event journal
→ deterministic DAG validation and scheduling
→ durable worker claim
→ capability-authorized execution
→ journaled state transition and result
→ replay and integrity verification
→ tenant-authorized WebSocket projection

Every run carries tenant, run, task, correlation, causation, specification,
policy, and artifact identity. Every event has a schema version, aggregate
sequence, and integrity-chain digest.

## Core components

| Component | Responsibility | Authority |
|---|---|---|
| API/control plane | Authentication, tenant resolution, request validation, submission and reads | No execution authority |
| Contracts | Versioned event and execution schemas | Contract authority |
| Event journal | Append-only event history, aggregate sequencing, digest chain | Authoritative |
| Scheduler | DAG validation, cycle detection, deterministic ordering and execution waves | Plan only |
| Worker fleet | Lease-based task claims, capability checks, bounded retries, result transitions | Executes authorized work |
| Replay/verifier | Reconstruct state and independently validate event and artifact integrity | Verification only |
| WebSocket projection | Deliver tenant-scoped journal updates | Read-only projection |
| Nexus AI | Workspaces, API keys, quotas, metering, billing and customer UI | Product/control plane |

## Determinism contract

A replay is valid only when the same canonical event history, policy versions,
artifact digests, and execution specifications reconstruct equivalent
authorized internal state. Wall-clock values, random values, model outputs,
and external side effects are inputs that must be captured as evidence; replay
must not repeat external side effects.

The scheduler uses deterministic topological waves. Nodes within one wave are
independent under the declared dependency graph. A stable lexical tie-breaker
makes plan generation independent of input ordering.

## Persistence and delivery

PostgreSQL is the transactional source of truth. Journal append, aggregate-head
advance, and any future outbox record that represents the append must commit in
one transaction. A dispatcher may publish committed outbox records to Kafka
at least once; consumers must be idempotent. Kafka is a transport, not the
system of record.

Redis may be introduced only for disposable coordination/cache workloads.
It must not hold the only copy of task state, event history, leases, or
idempotency decisions. ClickHouse is an analytics projection, not an authority.

## Worker safety invariants

- Claims are acquired with row locking and skip-locked semantics.
- A lease expires and can be reclaimed after worker loss.
- A monotonically increasing fencing generation prevents stale workers from
  committing after a claim has been superseded.
- Retries are bounded and limited to explicitly classified retryable failures.
- Side effects require declared capabilities and execution-time authorization.
- Idempotency keys bind tenant, run, task, operation, and immutable input digest.
- A worker must not acknowledge completion until its result and corresponding
  journal transition are durably committed.
- Replay reconstructs state but never invokes tools or repeats external effects.

The current worker implementation on the integration branch establishes
PostgreSQL-backed task materialization, claims, leases, and journal transitions.
It is not yet sufficient to claim the fencing, bounded retry, or atomic
journal-plus-result commit invariants above. Those are explicit implementation
gates, not assumed capabilities.

## Security boundaries

- Tenant identity is derived from authenticated credentials, never trusted from
  caller-controlled payload fields.
- Every read, claim, state mutation, and stream query is tenant-scoped.
- Tool access is deny-by-default and limited to a versioned capability set.
- Approval binds to the immutable action-plan digest, tenant, actor, policy
  version, target, and expiry; plan changes invalidate approval.
- Secrets are references to a secret manager and are excluded from prompts,
  logs, event payloads, and evidence.
- High-risk and irreversible operations require human approval.
- Security failures are fail-closed and do not fall back to in-memory state.

## Deployment topology

Initial production-shaped deployment:
- FastAPI API process (stateless)
- one or more stateless worker processes
- PostgreSQL primary with managed backups and tested restore
- external OpenTelemetry collector and metrics/logging backend
- Docker Compose for reproducible local integration
- Kubernetes/Helm/Terraform after worker and database failure gates pass

Kafka, Redis, ClickHouse, sandbox execution, and Kubernetes are not required to
prove the first durable execution contract. Add them only when the corresponding
throughput, isolation, or operational requirement is measured.

## Dependency-ordered release gates

1. **Journal gate:** canonical event envelope, tenant isolation, sequencing,
   digest chain, idempotency, migrations and PostgreSQL integration tests.
2. **Scheduler gate:** deterministic DAG validation, unknown-dependency and
   cycle rejection, stable execution waves. This change establishes this gate's
   pure scheduling contract.
3. **Worker gate:** atomic lease claims, fencing tokens, heartbeat, bounded
   retries, stale-worker rejection, crash recovery, and concurrent-claim tests.
4. **Transaction/outbox gate:** task outcome and journal transition committed
   atomically; outbox dispatch/retry/idempotency verified against a real broker.
5. **Replay/verification gate:** replay from journal only, digest verification,
   side-effect suppression, independent invariant checks, evidence export.
6. **VCIR gate:** typed intent/graph, SSA/CFG lowering, capability and side-effect
   declarations, verifier integration. WASM and formal proof tooling follow
   only where concrete proof obligations justify them.
7. **Nexus integration gate:** authenticated tenant/API-key model, quotas,
   usage metering, billing entitlements, and dashboard projections.
8. **Deployment gate:** migration ownership, secrets, network policy, SBOM,
   signed artifacts, restore drills, SLOs, alerting, and Kubernetes release
   evidence.

No release gate is passed by documentation alone. Each requires executable
tests and retained CI or operational evidence.
