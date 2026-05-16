# v3.2 P2 exit criteria

Operational analytics layer complete when all criteria below are satisfied.

## Deliverables

| Item | Status |
|------|--------|
| ADR-031 | ☑ |
| `ops_analytics_aggregate.py` | ☑ |
| `ops_visualize.py` | ☑ |
| `ops_archive.py` | ☑ |
| `generate_shift_handoff.py` | ☑ |
| `metrics_retention_policy.md` | ☑ |
| `make ops-analytics-validate` | ☑ |

## Quality gates

| # | Criterion | Verification | Met |
|---|-----------|--------------|-----|
| 1 | Analytics strictly offline/read-only | ADR-031; code review | ☑ |
| 2 | Retention bounded and enforced | rotate + archive tests | ☑ |
| 3 | No runtime path touched | No publisher/worker edits | ☑ |
| 4 | No network services added | CI tests offline | ☑ |
| 5 | Deterministic reports | Fixture snapshot tests | ☑ |
| 6 | Corrupt snapshot handling | skip + verify tests | ☑ |
| 7 | Operator reporting improved | shift handoff + SVG index | ☑ |
| 8 | Production-lite stability | `make ci-test` green | ☑ |

## Validation

```bash
make ops-analytics-validate
make ops-tooling-validate
make ci-test
```

## Sign-off

| Role | Date |
|------|------|
| Operator | |
| Engineering | |

**P2 status:** ☑ COMPLETE (engineering)
