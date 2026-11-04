# Skill Execution Contract

## State machine

States: requested, validated, authorized, queued, running, waiting_approval, verifying, succeeded, failed, cancelled, needs_reconciliation. Terminal states are succeeded, failed, and cancelled. needs_reconciliation is paused, not success.

Allowed transitions:
- requested → validated | failed
- validated → authorized | failed
- authorized → queued | waiting_approval | failed
- queued → running | cancelled
- running → running | waiting_approval | verifying | failed | needs_reconciliation
- waiting_approval → authorized | cancelled | failed
- verifying → succeeded | failed | needs_reconciliation
- needs_reconciliation → running | verifying | failed
- succeeded, failed, cancelled → no transitions

Retries are new attempts under the same task identity with a distinct attempt number. Terminal tasks cannot be silently reopened.

## Minimum event envelope

Every event includes event_id, event_type, schema_version, occurred_at (UTC), tenant_id, task_id, attempt, correlation_id, causation_id (nullable for root), skill_id, skill_version, manifest_digest, policy_version, actor_type, actor_id, payload_digest, and idempotency_key.

Payloads must not contain credentials, access tokens, raw secrets, or unnecessary personal data. Sensitive evidence is stored separately with access control and referenced by immutable identifier and digest.

## Approval record

An approval is integrity-protected and bound to tenant and actor, task ID, exact action-plan digest, tool/capability and target resource, side-effect class, expiry, policy version, and one-time-use/replay protection. Approval for one action does not authorize later steps or changed parameters.

## Retry and recovery

- Retry only errors classified as transient by both skill manifest and runtime policy.
- Enforce maximum attempts and exponential backoff with jitter in the runtime.
- Use expiring leases and monotonically increasing fencing tokens.
- Commit state transitions with compare-and-swap against expected version/fencing token.
- After worker death, lease expiry permits a new claim; stale worker commits are rejected.
- Before retrying an external side effect with an ambiguous result, reconcile the destination using the idempotency key or enter needs_reconciliation.
- Replay must never re-execute the external action represented by an event.

## Verification record

A successful task stores acceptance criteria and result per criterion, test command and exit status where applicable, evidence identifiers/digests, verifier identity/version, independent-check result when required, environment, source revision, timestamps, and final task state.

Narrative output alone is not proof. Missing evidence leaves the criterion unverified.

## Failure semantics

- stop: terminate the attempt and retain evidence.
- escalate: pause and surface the blocking reason to an operator.
- compensate: invoke only a separately authorized, declared compensation action; record both original and compensation outcomes.
- Unknown error types fail closed and are not retried automatically.
