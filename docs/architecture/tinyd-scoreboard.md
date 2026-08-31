# TinyD + Scoreboard canonical architecture

TinyD is the deterministic execution kernel. Scoreboard is the integrated assurance plane. They share one canonical event/evidence model; Scoreboard does not create competing execution truth.

## Authority

- TinyD: authoritative execution state and deterministic state transitions.
- Kafka: durable event stream, ordering, consumer delivery, and replay source.
- PostgreSQL: transactional/queryable ledger and projections. It is not a second execution engine.
- Evidence store: immutable evidence artifacts and attestations.
- Scoreboard: derived assurance, verification, provenance, audit, and ownership views.
- OpenTelemetry/Prometheus/Grafana: operational telemetry only; never the authoritative audit ledger.

## Exactly-once boundary

TinyD provides effectively-once business semantics through deterministic processing, idempotency keys, transactional state transitions, and deduplication. External systems that cannot participate in the transaction boundary must be treated as at-least-once and protected with their own idempotency mechanism.

## Mandatory contracts

`PolicyEngine`, `EvidenceWriter`, `EvidenceVerifier`, `ProvenanceResolver`, `IntegrityVerifier`, `ArtifactAttestor`, `OwnershipRegistry`, and `ReplayVerifier` are in-process interfaces/contracts. They are not independent microservices unless operational evidence later justifies extraction.

## Evidence

Every consequential execution fact is represented by a versioned event envelope containing tenant, execution, actor, capability, operation, policy, code/artifact/input/output digests, provenance, idempotency, and integrity metadata. Sensitive values are excluded from canonical payloads.

The evidence ledger is append-only and hash-chained per tenant. PostgreSQL migration `001_canonical_evidence.sql` defines the persistent model; `002_evidence_immutability.sql` blocks updates and deletes.

## Verification

Evidence production and verification are separate trust responsibilities. Verification results are themselves immutable evidence. Replay verification re-evaluates the recorded event sequence and compares deterministic integrity state. Missing evidence or failed verification is never treated as verified.

## Cryptographic trust

Artifact attestations use Ed25519. Trust keys are identified by signer and version, can be revoked, and are resolved through an explicit trust root. Private signing material must remain outside repository events, evidence, telemetry, and provenance.

## Provenance and ownership

Provenance has a controlled vocabulary of node types and relationships. Ownership records represent evidence-backed relationships such as `AUTHORED_BY`, `LICENSED_UNDER`, `ASSIGNED_BY`, or `ACQUIRED_UNDER`; the system does not infer legal ownership from an application flag.

## Lifecycle

`SPEC -> POLICY -> CODE -> BUILD -> ATTEST -> EXECUTE -> OBSERVE -> RECORD -> VERIFY -> PROVE -> AUDIT`

Release gates are fail-closed: no evidence means not verified; failed tests or incomplete dependencies block completion.
