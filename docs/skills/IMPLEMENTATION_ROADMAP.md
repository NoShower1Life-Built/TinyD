# Skill System Implementation Roadmap

This roadmap is dependency-ordered. A task is complete only when its commit, tests, and captured results provide evidence.

## Stage 1 — Contract foundation
- [x] Add Python manifest validator with fail-closed top-level validation.
- [x] Enforce identity, semantic version, typed IO declarations, unique names, permissions, risk/autonomy rules, sequential workflow, bounded retry policy, and verification fields.
- [x] Add unit tests for valid manifests and representative invalid cases.
- [ ] Run the test suite in a reproducible environment and record actual output.
- [ ] Add JSON Schema and verify parity with the Python validator.
- [ ] Add compatibility tests and published manifest examples.

## Stage 2 — Runtime integration
- [ ] Inspect current TinyD task/event/state implementation before adding abstractions.
- [ ] Map skill tasks onto the canonical journal and existing state machine; no competing scheduler or event store.
- [ ] Add manifest digesting and immutable skill-version resolution.
- [ ] Add execution-time authorization and tenant-scoped capability resolution.
- [ ] Add approvals bound to immutable action-plan digests.
- [ ] Add lease/fencing/idempotency and crash-recovery tests for skill tasks.

## Stage 3 — Evidence and verification
- [ ] Persist per-step evidence references and acceptance-criterion outcomes.
- [ ] Add independent verifier interfaces and fail-closed release gates.
- [ ] Prove replay reconstructs state without repeating external side effects.
- [ ] Test ambiguous external outcomes and reconciliation.
- [ ] Produce a machine-readable verification bundle with source revision and artifact digests.

## Stage 4 — First operational skills
- [ ] Repository Audit: read-only GitHub adapter, path/ref provenance, finding schema, tests.
- [ ] Project Memory / Decision Ledger: tenant isolation, append-only decision events, source references.
- [ ] Watcher / Sentinel: durable cursor/state, deduplication, bounded polling, change significance tests.
- [ ] Repository-to-Production: build/test/deploy/rollback workflow with approval gates.
- [ ] Chief of Staff: orchestration only after the preceding contracts and runtime gates pass.

## Stage 5 — Integrations
For each integration (GitHub, Vercel, OpenAI Platform, Hugging Face, Canva, Ads Manager, email/calendar), record actual tool schema, authentication scope, rate limits, retry semantics, data sensitivity, side-effect classes, and test strategy. Integration write access stays disabled until review and explicit policy configuration.

## Exit criteria
- Contract schema and validator agree on accepted/rejected manifests.
- Unit and integration tests run in CI; skipped tests are not represented as passing.
- Tenant isolation, authorization, idempotency, lease fencing, crash recovery, replay, and evidence integrity have executable tests.
- High-risk writes are denied without valid action-bound approval.
- Reproducible build and SBOM are produced.
- At least one read-only skill runs through the real TinyD journal and returns verifiable evidence.
- No production-readiness claim until deployment and production-observation evidence exists.
