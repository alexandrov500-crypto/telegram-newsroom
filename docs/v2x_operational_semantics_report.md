# v2.x operational semantics report

Verification and documentation phase — **no runtime redesign**.

## Operational Semantics Maturity

- Invariants, forbidden states, recovery semantics, and consistency matrix published under `docs/semantics/`.
- Governance ties semantics changes to ADR/matrix discipline.
- Read-only `tools/semantics_guardrails.py` for operator/CI hints.

## Invariant Verification Status

| Area | Doc | Test / tool |
|------|-----|-------------|
| Retry order (safe vs legacy) | operational_invariants | `tests/semantics/test_retry_semantics.py` |
| Publish lock strict | operational_invariants | `tests/semantics/test_lock_semantics.py` |
| Forbidden env | forbidden_states | `semantics_guardrails.py` |
| Frozen contracts | semantics_governance | guardrails + contracts |
| Recovery bounded | recovery_semantics | `test_recovery_expectations.py` |

## Recovery Semantics Reliability

- Guarantees and **non-guarantees** explicitly listed.
- Degraded modes documented (WARN, strict deny, T3).
- Aligns with v1.1 chaos and v1.9 recovery intelligence (read-only).

## Forbidden State Coverage

- Registry covers multi-worker, recovery, retention, locks, Redis fallback.
- Recoverability levels guide operator triage.

## Assumption Stability Assessment

- [assumption_audit.md](semantics/assumption_audit.md) lists filesystem, Redis, SQLite, Telegram, clock, backup assumptions.
- Impact/mitigation pairs reduce surprise failures.

## Remaining Safety Gaps

| Gap | Notes |
|-----|-------|
| Exactly-once | Not claimed; idempotency operator responsibility |
| Cross-node | Unsupported |
| Live restore | Forbidden; detection advisory |
| Telegram undo | Not supported |
| Formal proof | Out of scope |

## Recommended Long-Term Verification Strategy

1. Extend `tests/semantics/` when opt-in flags add behavior (trace assertions only).
2. Link nightly JSON to guardrails (read-only correlation).
3. Annual semantics review with architecture validate.
4. v2 only if contract freeze changes — re-write semantics docs in migration program.

## Operational Invariant Coverage

See [operational_invariants.md](semantics/operational_invariants.md) — queue, retry, lock, snapshot, recovery order, evidence, WAL, scheduler, bounded diagnostics.

## Forbidden State Coverage

See [forbidden_states.md](semantics/forbidden_states.md).

## Recovery Semantics Confidence

See [recovery_semantics.md](semantics/recovery_semantics.md).

## Consistency Model Assessment

See [consistency_matrix.md](semantics/consistency_matrix.md).

## Assumption Risk Assessment

See [assumption_audit.md](semantics/assumption_audit.md).

## Remaining Ambiguity Areas

- Idempotency of custom job handlers (application-level)
- Redis cluster / sentinel (unsupported)
- Partial Telegram API failures mid-batch

## Unsupported Safety Guarantees

- HA, multi-region, zero-downtime restore, autonomous remediation, exactly-once queue

## Recommended Future Verification Priorities

1. DLQ replay semantics integration tests (bounded)
2. Partial OUTPUT_DIR detection in operator nightly wrapper
3. Semantics changelog section in release notes template

## Validation

```bash
make semantics-validate
make ci-test
make governance-validate
make architecture-validate
```

## Backward compatibility

- No runtime contract changes
- No evidence schema changes
- No default-on behavior changes
