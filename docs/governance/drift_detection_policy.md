# Drift detection policy (v3.2 stewardship)

Detects **freeze breach** and **scope creep** before they become platform evolution.

## Drift categories

| Drift type | Indicator |
|------------|-----------|
| Runtime/tooling coupling | `publisher` imports in `tools/ops_*`; metrics driving retry |
| Schema drift | `validate_ops_schema` FAIL; unknown required fields |
| Uncontrolled scope growth | New ops subsystem without ADR-035+ |
| Operational complexity creep | New daemon, scheduler for ops, background worker |
| Tooling/network dependency | `requests`/`httpx` in offline export tools |

## Detection mechanisms

| Mechanism | Frequency |
|-----------|-----------|
| `tools/check_freeze_integrity.py` | Weekly + every tooling PR |
| `validate_ops_schema.py` | Weekly |
| `make stewardship-audit-validate` | Monthly / PR |
| Manual PR review | Every merge |
| Quarterly maturity review | 90d |

## Escalation criteria

| Severity | Condition | Response |
|----------|-----------|----------|
| S1 | Runtime path changed under tooling PR | Revert; runtime ADR required |
| S2 | Freeze integrity FAIL | Block merge; investigate |
| S3 | Schema WARN (legacy diagnostics) | Document; plan additive fix |
| S4 | Doc/link drift | Fix in docs-only PR |

## Remediation path

1. Identify drift class (table above).
2. Run `check_freeze_integrity.py` and attach report.
3. If S1/S2: revert or split PR (runtime vs tooling).
4. If scope expansion intended: stop — open ADR-035+ program.
5. Re-run `make stewardship-audit-validate`.

## Freeze breach handling

1. Record incident in PR/issue with `freeze-breach` label.
2. Engineering lead confirms whether tag `v3.2-operational-tooling-freeze` baseline was violated.
3. Restore compliance or publish **new** freeze tag only after ADR + full validation (not silent moves).
4. Update [offline_recovery_certification.md](../releases/offline_recovery_certification.md) if recovery path changed.

## References

- [ADR-034](../architecture/ADR-034-v3-2-finalization-and-stewardship.md)
- [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md)
