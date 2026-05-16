# Final acceptance criteria (v3.1 merge)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Staging live validation successful | **PARTIAL** | Bounded CI PASS; live connect PENDING operator `.env` |
| Operator workflow signed off | **PARTIAL** | Code-path PASS ([operator_staging_signoff.md](operator_staging_signoff.md)) |
| No uncontrolled publishes | **PASS** | Zero automated publishes; cap documented |
| No duplicate delivery observed | **PASS** (CI) | Lock contention tests |
| Diagnostics stable | **PASS** | schema v2 OK |
| Rollback documented | **PASS** | rollout + staging checklist |
| Governance constraints respected | **PASS** | ≤5 cap, opt-in live, no runtime drift |
| Readiness grade **A** | **A−** | Upgrade to **A** after operator live items |

## Merge gate commands

```bash
make ci-test
make live-validation-validate
make governance-validate
make resilience-validate
make staging-validate
```

## Pre-merge operator actions

1. Complete [live_staging_signoff.md](live_staging_signoff.md) live rows
2. Sign [operator_staging_signoff.md](operator_staging_signoff.md)
3. `python3 tools/staging_environment_verify.py --strict` → OK on staging host
