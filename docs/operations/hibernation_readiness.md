# Hibernation readiness

**Goal:** Confirm the newsroom can live **months unchanged** while remaining calm, bounded, and transferable.

Not a certification program — a **checklist** for custodians over 30–90 days.

Philosophy: *Infrastructure hibernation readiness* = intentional non-intervention is safe.

---

## Readiness criteria (sustained 30–90 days)

Mark each week; hibernation-ready when **all** hold across the window:

| # | Criterion | How to verify |
|---|-----------|----------------|
| 1 | Digest remains quiet | `weekly_calmness_check` · invisible/finalization early returns |
| 2 | Runtime validation stable | `infrastructure_validation_ok` or observe without action |
| 3 | Persistence bounded | `bounded_persistence_ok` · growth rate &lt; 0.5 typical |
| 4 | No expansion pressure | No proposals for new governance layers |
| 5 | No governance drift | Cohesion not FRAGMENTED; no recursion signals |
| 6 | No operator escalation | Interventions rare, evidence-backed |
| 7 | No telemetry fragmentation | `collector_integrity_ok` · canonical stability |
| 8 | Restart survivability healthy | `restart_survivability_ok` after deploys |
| 9 | Transferability preserved | Checklist + snapshot still accurate |

---

## Weekly pass (minimal)

```bash
python3 scripts/weekly_runtime_validation.py --record
```

- [ ] Criteria 1–3, 7–8 from script output
- [ ] Criteria 4–6 from judgment + [weekly_non_intervention_log.md](weekly_non_intervention_log.md)

---

## Monthly pass

```bash
python3 scripts/monthly_stability_review.py
```

- [ ] `monthly_verdict` = `stable` (or `observe` with no architecture work)
- [ ] Record in [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md)

---

## Hibernation-ready declaration

When 30–90 days sustained, custodian may note in `STEADY_STATE_STATUS.md`:

> **Hibernation-ready:** calm continuity verified; custodianship mode; intervention scarcity active.

This does **not** mean stop security patches or emergency repair.

---

## Not required for readiness

- New code or tooling
- Dashboards or automation
- Governance changes
- “Improvement” commits

---

## Related

- [infrastructure_custodianship.md](infrastructure_custodianship.md)
- [operational_time_capsule.md](../architecture/operational_time_capsule.md)
