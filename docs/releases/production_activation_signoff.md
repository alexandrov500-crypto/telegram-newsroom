# Production activation sign-off

Final acceptance for production-lite steady-state after 72h stability window.

## Prerequisites (all required)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Merge complete + tag `v3.1-production-lite` | ☐ |
| 2 | Staging grade **A** | ☐ |
| 3 | Controlled activation runbook completed | ☐ |
| 4 | 72h stability window completed | ☐ |
| 5 | Rollback tested (`DRY_RUN` drill) | ☐ |

## Steady-state confirmation

| # | Criterion | Status |
|---|-----------|--------|
| 1 | 72h without critical incident | ☐ |
| 2 | No uncontrolled publishes | ☐ |
| 3 | No duplicate deliveries | ☐ |
| 4 | Bounded retries respected | ☐ |
| 5 | Diagnostics reliable on schedule | ☐ |
| 6 | Operator workflow sustainable | ☐ |
| 7 | Governance caps continuously enforced | ☐ |

## Metrics attestation (day 3)

| Metric | Observed | OK |
|--------|----------|-----|
| `publish_failures` | | ☐ |
| `publish_retries` | | ☐ |
| `telethon_reconnects` | | ☐ |
| `telethon_flood_waits` | | ☐ |
| `publish_lock_contention` | | ☐ |

## Sign-off

| Role | Name | Date |
|------|------|------|
| Operator owner | | |
| Engineering | | |

**Production-lite steady-state declared:** ☐ Yes ☐ No (extend 72h)
