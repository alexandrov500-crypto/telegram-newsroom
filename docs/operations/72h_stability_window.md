# First 72h stability window

Mandatory observation period after production-lite activation (P2). **No config churn, no feature deploys.**

## Policy

| Rule | Detail |
|------|--------|
| Config churn | **Forbidden** except `DRY_RUN` emergency |
| Feature deployment | **Forbidden** |
| Publish oversight | Manual approval every publish |
| Diagnostics | Every **4 hours** minimum |
| Publish volume | **≤5/day** week 1 (operator enforced) |
| Incident logging | All MEDIUM+ to ops log |

## Review schedule

| Hour | Activity |
|------|----------|
| 0 | Baseline diagnostics; C4 checkpoint |
| 4, 8, 12, … | Diagnostics + log scan |
| 24 | Day-1 summary: counters, incidents |
| 48 | Mid-window review |
| 72 | Steady-state decision |

## Confirmation checklist

| Signal | Confirm |
|--------|---------|
| Retry rates stable | `publish_retries` not trending up |
| No duplicate publish | Channel audit + lock metrics |
| Reconnect normal | `telethon_reconnects` ≤3/day typical |
| No stuck locks | No hung `publishing` > TTL |
| No silent failures | Failed drafts logged; no orphan channel posts |

## Healthy ranges (72h aggregate)

| Metric | Target |
|--------|--------|
| Critical incidents | 0 |
| Duplicate deliveries | 0 |
| `publish_failures` | 0–1 with documented cause |
| `telethon_flood_waits` | <10 total |
| Unplanned `DRY_RUN` | 0 |

## Exit criteria (enter steady-state)

- [ ] 72h without critical incident
- [ ] Operator workflow sustainable (fatigue notes addressed)
- [ ] Rollback drill completed once
- [ ] Diagnostics reliable on schedule
- [ ] Governance caps respected
- [ ] Sign-off in [production_activation_signoff.md](../releases/production_activation_signoff.md)

## If violated

1. `DRY_RUN=true`
2. Open incident per [incident_response.md](../runbooks/incident_response.md)
3. Extend 72h window after fix
