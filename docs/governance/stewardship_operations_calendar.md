# Stewardship operations calendar

> **Superseded (cadence):** Repository is **DORMANT** (ADR-038). Use [dormancy_operations_policy.md](dormancy_operations_policy.md) for **90d / 180d** preservation and **incident-only** full validation. This calendar remains as historical context for the post-freeze stewardship window.

Cadence for **v3.2 offline operational tooling** after tag `v3.2-operational-tooling-freeze`. Runtime production-lite ops follow separate runbooks.

## Every 24 hours (operator)

| Task | Action | Owner |
|------|--------|-------|
| Diagnostics review | Scan latest `ops_metrics` snapshot or run `ops_metrics_snapshot.py --summary-only` | Operator on-call |
| Archive spot-check | `ops_archive.py --verify-only` on sample path if archives exist | Operator on-call |

**Sign-off:** optional log entry in shift notes.

## Every 7 days (operator + engineering)

| Task | Action | Owner |
|------|--------|-------|
| Release kit | `build_ops_release_kit.py`; verify checksums | Operator |
| Reproducibility | `OPS_FROZEN_UTC=… make stewardship-validate` on CI or staging checkout | Engineering |
| Archive rotation | `ops_archive.py` per [metrics_retention_policy.md](../operations/metrics_retention_policy.md) | Operator |

**Sign-off:** kit `README.txt` date noted in handoff.

## Every 30 days (engineering)

| Task | Action | Owner |
|------|--------|-------|
| Schema governance | `validate_ops_schema.py` on production `var/ops_history` | Engineering |
| Recovery drill | [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md) | Operator + engineering |
| Stewardship chain | `make stewardship-validate` | Engineering |
| Freeze integrity | `check_freeze_integrity.py` | Engineering |

**Sign-off:** [offline_recovery_certification.md](../releases/offline_recovery_certification.md) operator section.

## Every 90 days (engineering + release manager)

| Task | Action | Owner |
|------|--------|-------|
| Maturity reassessment | Review [operational_maturity_assessment.md](../releases/operational_maturity_assessment.md) | Engineering |
| Tooling debt | Review open issues labeled `tooling-debt` | Engineering |
| Freeze policy | Review [v3_2_tooling_freeze.md](../releases/v3_2_tooling_freeze.md) exceptions | Release manager |
| Stewardship audit bundle | `make stewardship-audit-validate` | Engineering |

**Sign-off:** quarterly note in PR or internal log; ADR exception if policy change needed.

## Escalation paths

| Condition | Escalate to | Action |
|-----------|-------------|--------|
| `freeze_integrity` FAIL (runtime diff) | Engineering lead | Stop hotfix; separate runtime ADR |
| Schema FAIL | Engineering + operator | Isolate corrupt snapshots |
| Recovery drill FAIL | Operator on-call | Follow hotfix procedure |
| Platform/feature request | Release manager | Reject or open ADR-035+ |

## References

- [long_term_stewardship.md](long_term_stewardship.md)
- [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md)
- [MAINTAINERS_GUIDE.md](../MAINTAINERS_GUIDE.md)
