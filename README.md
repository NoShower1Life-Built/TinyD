# TinyD

TinyD is a deterministic, event-sourced execution runtime for AI orchestration and distributed systems.

This repository now treats engineering control state as a first-class machine-readable concern. The repository is the source of truth; dashboards and other interfaces are projections of that state.

## Control model

The intended lifecycle is:

```text
Requirement
  -> Implementation
  -> Dependency
  -> Impact Analysis
  -> Machine-Generated Task
  -> Execution Definition
  -> Actual Execution
  -> Evidence
  -> Verification
  -> Release Gate
```

A material source change can propagate through the reverse path:

```text
Source Change
  -> Impact Analysis
  -> Evidence stale/invalid
  -> Verification recalculated
  -> Dependent tasks blocked
  -> Queue recomputed
```

The purpose is to prevent requirements, dependencies, execution state, evidence, and verification from drifting apart during iterative development.

## Machine-readable controls

The current control layer is intentionally dependency-light and uses JSON plus the Python standard library.

```text
control/
  control-model.json       Canonical predicates and release rules
  state-machine.json       Execution states and allowed transitions
  requirements.json        Requirement records and test references
  tasks.json               Dependency-aware task records

tests/
  mappings.json            Requirement -> executable test mapping
  test_control_model.py    Executable control invariants

scripts/
  control_validate.py      Repository invariant validator
  plan.py                  Deterministic dependency-aware queue generator
```

## Enforced invariants

The validator is designed to detect, rather than merely document, conditions such as:

- a requirement with no test
- a requirement referencing a missing test mapping
- a mapped test whose executable file is absent
- a task referencing a missing dependency
- a task referencing an unknown requirement
- a task marked complete while a dependency is incomplete
- invalid execution-state transitions
- forbidden execution-to-verification shortcuts
- an empty verification predicate set
- an empty readiness predicate set

Run the validator with:

```bash
python3 scripts/control_validate.py
```

The dependency-aware planner can be inspected with:

```bash
python3 scripts/plan.py
```

The planner validates missing dependencies and cycles before producing an ordered queue. It derives `READY` or `BLOCKED` from dependency state and includes blocking reasons in its output.

## Verification model

Verification is derived rather than manually asserted. The control model requires the following predicates:

```text
requirement_exists
implementation_complete
dependencies_satisfied
required_tests_exist
required_tests_pass
execution_exists
evidence_exists
evidence_valid
evidence_matches_source
no_blocking_findings
```

A verification claim without applicable evidence is therefore not sufficient.

## Execution state machine

Execution uses explicit states:

```text
PLANNED
  -> READY
  -> DISPATCHED
  -> RUNNING
  -> SUCCEEDED | FAILED | TIMED_OUT | CANCELLED
```

Terminal success is not equivalent to verification. Evidence and verification remain separate downstream controls.

## Release gate

The target release gate is derived from repository state. A release should only become eligible when required requirements are verified, required tests pass, dependencies are clear, required evidence is valid, and no blocking findings remain.

The current repository should not be represented as production-ready solely because this control model exists. The remaining work includes complete evidence invalidation, canonical state evaluation across all runtime components, immutable execution/event history, end-to-end execution proof, and machine-enforced release gating.

## UI principle

Any control-plane UI should be treated as a read-only projection plus controlled commands against the authoritative control plane.

It must not invent progress percentages or independently decide whether a requirement is verified.

The intended UI surfaces are:

```text
Overview
Requirements
Dependency Graph
Impact Analysis
Execution Queue
Runner
Evidence Ledger
Verification
Release Gate
External Reconciliation
```

Iframe rendering should remain isolated from parent-page CSS and JavaScript, avoid unnecessary external assets, and work across desktop, tablet, and mobile dimensions.

## External reconciliation

External arbitrage/reconciliation belongs behind an adapter boundary. Quote ingestion, normalization, freshness validation, comparison, policy evaluation, execution authorization, evidence, and audit must remain distinct stages.

A calculation or UI view must not be represented as an executed financial action.

## Development operating model

Every development batch follows:

```text
Inspect
  -> Model
  -> Identify blockers
  -> Analyze impact
  -> Generate queue
  -> Implement
  -> Test
  -> Capture evidence
  -> Verify
  -> Recalculate state
  -> Invalidate stale evidence
  -> Replan
  -> Update scoreboard
  -> Evaluate release gate
```

The word `next` does not authorize skipping this cycle. The next task must be selected from the current machine-derived state.

## Definition of done

Code being written is not, by itself, completion.

The applicable completion chain is:

```text
Requirement exists
  -> implementation identified
  -> dependencies satisfied
  -> tests exist
  -> tests execute
  -> tests pass
  -> execution recorded
  -> evidence generated
  -> evidence bound to the correct source
  -> evidence valid
  -> verification derived
  -> no blocking findings
  -> downstream state recalculated
  -> release gate updated
```

If the chain stops, the repository must expose the gap.

## Current status

The control architecture is established, but enforcement is incremental. The machine-readable control model, state machine, requirement/test mapping, executable control tests, validator, and dependency-aware planner are now present on the refinement branch.

The following remain explicit implementation targets:

```text
Canonical state evaluator
Complete evidence invalidation
Immutable event/execution history
Full execution/evidence integration
Machine-derived scoreboard
Machine-enforced release gate
Complete reverse-impact propagation
Replay and recovery verification
End-to-end release proof
```

Do not convert these targets into claims of completion until the repository can produce the corresponding evidence.

## License

Licensed under the Apache License 2.0. See `LICENSE` for the complete license text.

## Attribution

Copyright © 2026 NoShower1Life-Built.

TinyD is the execution runtime foundation of the Nexus AI platform.
