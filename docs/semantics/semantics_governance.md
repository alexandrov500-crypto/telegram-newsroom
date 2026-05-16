# Operational semantics governance

How invariants evolve without formal-methods bureaucracy.

## How invariants evolve

1. Propose change in issue/ADR with [evolution_decision_matrix.md](../architecture/evolution_decision_matrix.md).
2. Update semantics docs in same PR as behavior change (if any).
3. Extend `tests/semantics/` with deterministic check.
4. Run `make semantics-validate`.

Default: **docs + tests only** for clarification releases.

## When semantics may change

| Change type | Gate |
|-------------|------|
| Clarification (no code) | Semantics PR + contract tests |
| Opt-in flag behavior | feature_flag_governance + ADR note |
| Default behavior change | Major version or forbidden |
| New frozen artifact | v2 program |
| Recovery tool output shape | Minor if backward compatible |

## Major-version semantics policy

- Breaking recovery or inspection semantics requires v2 gates ([v2_transition_strategy.md](../architecture/v2_transition_strategy.md)).
- Operators receive upgrade runbook + explicit NOT guaranteed list updates.

## Compatibility expectations

- 1.x: schema v1; semantics docs may clarify without breaking contracts.
- Forbidden states registry may grow (more explicit warnings).
- Guardrails may add detections (read-only).

## Operator notification expectations

- CHANGELOG for user-visible semantic fixes.
- Runbook link when forbidden state newly detected by tooling.
- No silent narrowing of recovery guarantees without release note.

## Invariant freeze rules

Frozen without major version:

- 14 runtime artifact names and schema v1
- 11 inspection CLI commands
- Default-off reliability flags preserving v1.0.0 paths
- At-least-once queue model

May evolve with opt-in:

- `WORKER_RETRY_SAFE`, `PUBLISH_LOCK_STRICT`, diagnostics flags

## Verification discipline

```bash
make semantics-validate
make ci-test
make architecture-validate
```

Semantics changes without tests require explicit ADR waiver (discouraged).
