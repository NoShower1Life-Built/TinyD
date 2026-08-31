# TinyD Assurance Boundary Contract

This document defines the canonical trust boundaries between execution, evidence, provenance, cryptographic trust, replay, and tenant context. These are contracts inside the monorepo; they are not service boundaries.

## 1. Event boundary

`EventEnvelope` is the canonical execution fact. Producers establish `tenant_id`, `execution_id`, actor/capability, policy version/digest, idempotency key, payload, parent event, and integrity digest. Consumers MUST verify integrity before materializing evidence. Consumers MUST NOT mutate an event or create a competing execution truth.

## 2. Evidence boundary

`EvidenceWriter` converts verified canonical events into append-only evidence. Evidence MUST be tenant-scoped, idempotent, hash-chained, digest-addressed, and free of secret-bearing values. PostgreSQL is the authoritative queryable evidence ledger. Kafka is the durable event transport/history and is not a second evidence ledger.

## 3. Provenance boundary

`ProvenanceResolver` owns canonical relationships between policy, source, build, artifact, attestation, execution, evidence, and verification. A provenance edge MUST identify tenant, relationship type, subject/object identifiers or digests, and its originating canonical event/evidence context. Client-side graph reconstruction is non-authoritative.

## 4. Cryptographic trust boundary

`IntegrityVerifier` verifies event/evidence digests. `ArtifactAttestor` binds an artifact digest to a signed attestation. `EvidenceVerifier` verifies evidence independently. Trust is anchored by versioned trust roots and key lifecycle metadata. Verification MUST fail closed when a key, algorithm, signature, digest, or trust-root relationship is invalid or unavailable.

## 5. Replay boundary

`ReplayVerifier` consumes canonical events independently of the normal execution result. It verifies ordering, parent relationships, event integrity, deterministic state transitions, and the resulting verification digest. Replay output is evidence about replay verification, not an execution event that can overwrite execution truth.

## 6. Tenant boundary

Tenant context is established at the authenticated control-plane boundary and propagated as trusted context. It MUST remain attached to events, evidence, provenance, verification, replay, artifacts, and ownership records. PostgreSQL RLS is the final storage enforcement layer. Tenant identifiers MUST NOT be accepted as an authorization substitute merely because they appear in client payloads.

## 7. Authority model

- TinyD kernel: execution authority.
- Kafka: canonical event transport/history.
- PostgreSQL: authoritative evidence/projection ledger.
- Scoreboard: assurance projection.
- OpenTelemetry/Prometheus/Grafana: non-authoritative telemetry.
- Verification contracts: independent assurance functions.

## 8. Required invariants

1. One canonical event/evidence model.
2. No competing execution truth.
3. Kafka and PostgreSQL have distinct responsibilities.
4. Exactly-once means idempotent/effectively-once semantics.
5. Evidence generation and verification remain separate trust domains.
6. Policies are immutable/versioned.
7. Artifacts are digest-addressed.
8. Provenance relationships are canonical.
9. Replay is independently verifiable.
10. Secrets never become evidence.
11. Tenant isolation spans the entire evidence pipeline.
12. Telemetry is never authoritative ledger state.
13. Cryptographic verification has an explicit trust-root/key lifecycle.
14. Interfaces remain contracts rather than premature microservices.
