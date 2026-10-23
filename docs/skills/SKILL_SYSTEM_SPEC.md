# TinyD Skill System — Specification v1

Status: Proposed implementation baseline. The contract validator and regression tests are implementation artifacts; no skill scheduler, tool executor, durable skill-task state machine, or production deployment is claimed here.

## Objective

Define skills as versioned, testable, permission-bounded capabilities under TinyD's existing execution authority. Skills describe workflows; they do not become competing schedulers, own infrastructure side effects, or treat model output as authorization.

## Architectural placement

- Nexus AI is the product/UI and tenant-facing policy surface.
- TinyD is the sole execution authority: durable task state, event journal, idempotency, leases, retries, authorization checks, and execution evidence.
- Skills are versioned capability packages containing a manifest, implementation adapter, tests, and documentation.
- VCIR expresses constrained intent, execution graph, side-effect classes, capability requirements, and verification obligations.
- The security layer supplies identity, tenant boundaries, and policy enforcement where implemented by the host.

A skill must not create a second scheduler, bypass the journal, access another tenant's state, or perform a side effect directly when it must pass through TinyD's authorized execution path.

## Initial portfolio, in dependency order

1. Skill Contract Validator — manifest shape and safety invariants. Validator and regression tests are implemented in this branch; runtime enforcement is not.
2. Repository Audit — read-only repository reconnaissance, evidence-backed findings, risk classification, and verification gaps.
3. Project Memory / Decision Ledger — durable tenant-scoped project state and append-only decisions with source references.
4. Watcher / Sentinel — scheduled polling through the existing runtime boundary, canonical state comparison, deduplication, and significance thresholds.
5. Repository-to-Production workflow — only after permissions, idempotency, evidence capture, and deployment gates are proven.
6. Chief-of-Staff orchestrator — last; selects existing skills using explicit contracts and cannot bypass their policies.

Research, Ads Manager, Canva, email, calendar, and Vercel integrations should be registered as adapters only after their concrete tool contracts, permission scopes, error models, and testability are documented. Connector availability is not proof that an action is safe or verified.

## Required manifest

Each skill declares contract version, stable ID, semantic version, purpose, triggers, typed inputs and outputs, allowed tools, read/write/approval permissions, risk, autonomy, sequential workflow steps with success conditions, retry/idempotency policy, compensation action where applicable, acceptance criteria, required evidence, and independent-check requirements.

The schema is closed by default: unknown top-level fields fail validation until a contract version explicitly adds them. Semantic versions use MAJOR.MINOR.PATCH, optional prerelease, and optional build metadata; numeric prerelease identifiers cannot contain leading zeroes.

## Permission semantics

- `read` declares read capabilities.
- `write` declares possible write capabilities; declaration alone does not authorize execution.
- `requires_approval` must be a subset of `write` and marks write capabilities that always need an approval gate.
- For high/critical risk skills, every declared write capability must be approval-gated.
- Bounded autonomous skills are low-risk only and cannot declare approval-gated actions or financial, destructive, or production writes.
- The runtime must independently authorize every action against tenant policy and the approval bound to the exact action plan. Manifest validation never grants permission.

## Failure and compensation semantics

The retry policy has a bounded attempt count, declared retryable error classes, and a stable idempotency-key expression. Unknown errors fail closed. A manifest selecting `on_exhaustion: compensate` must identify a non-empty `compensation_action`; all other exhaustion modes must set it to null. This declaration is not authorization to execute compensation: the runtime must separately authorize it and record the outcome.

## Execution lifecycle

discover → validate manifest → resolve tenant and identity → authorize capabilities → persist requested task → claim with lease → execute step → append result/evidence event → verify acceptance criteria → commit terminal state

The runtime must make every transition durable and idempotent. A worker crash must not produce an untracked external side effect. External actions need a stable idempotency key or a documented reconciliation/compensation strategy.

## Evidence states

- Declared: present in a manifest.
- Implemented: code exists.
- Unit-tested: test ran and passed.
- Integration-tested: connected dependencies were exercised.
- Independently verified: a separate check confirmed the result.
- Deployed: a deployment record exists.
- Production-observed: production telemetry confirms behavior.

A skill must not claim a higher state than evidence supports.

## Safety invariants

- Default to read-only.
- Model text never grants permissions.
- A tool must be on the skill allowlist and permitted by tenant policy.
- High/critical risk operations require explicit approval for every declared write capability.
- Sending messages, changing production, merging, deleting, or spending money must be separately authorized.
- Bounded autonomous mode is restricted to low-risk, reversible work and cannot perform production, financial, or destructive writes.
- Authorization is checked at execution time, not only during planning.
- Approval binds to an immutable action-plan digest, target, tenant, actor, policy version, expiry, and one-time-use/replay protection; material changes invalidate it.
- Secrets are referenced through a secret manager, never embedded in manifests, logs, prompts, or evidence.
- Cross-tenant resource lookups must include and verify tenant identity.
- Denials and failures are journaled without leaking secrets.

## Operational invariants

- Every execution has task ID, correlation ID, tenant ID, skill ID/version, manifest digest, policy version, and idempotency key.
- Retries are bounded and limited to declared transient errors.
- Workers claim tasks with expiring leases and fencing tokens; stale workers cannot commit state.
- Journal/outbox writes are transactional where they share a database.
- Replay reconstructs internal state from canonical events; replay never repeats external side effects.
- Side-effect outcomes are represented as events and reconciled after ambiguous failures.
- Schemas are versioned and migrations have one owner.
- Observability includes structured logs, metrics, traces, and audit evidence without secrets.
- Releases are gated by tests, security checks, dependency/SBOM checks, and an explicit evidence bundle.

## Non-goals for v1

No unrestricted self-modification, no generated executable code trusted without review, no open-ended tool access, no second scheduler, no marketplace, and no autonomous production deployment before lower-level controls are verified.
