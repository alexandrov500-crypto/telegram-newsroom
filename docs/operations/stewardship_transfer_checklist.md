# Stewardship transfer checklist

Institutional continuity for a new operator or engineer. **Not a runbook platform** — a handoff checklist.

---

## Before you operate

- [ ] Read [institutional_architecture_snapshot.md](../architecture/institutional_architecture_snapshot.md)
- [ ] Read [governance_surface_freeze.md](../architecture/governance_surface_freeze.md)
- [ ] Read [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md)
- [ ] Confirm [operational_preservation_mode.md](operational_preservation_mode.md) discipline

---

## Runtime

| Task | Command / location |
|------|-------------------|
| Health (local) | `scripts/production_health_verify.sh` or health endpoint per deploy docs |
| Operator service | `deploy/systemd/newsroom-operator.service` or `deploy/docker-compose*.yml` |
| Safe restart | Graceful stop → start operator; verify logs `digest_scheduler_started` |
| Post-restart validation | `python3 scripts/weekly_runtime_validation.py` |
| Weekly ritual | `python3 scripts/weekly_runtime_validation.py --record` |
| Monthly review | `python3 scripts/monthly_stability_review.py` |

---

## Operational signals (healthy)

| Signal | Healthy expectation |
|--------|---------------------|
| Digest | ≤4 lines when invisible/finalization quiet; early return, not long stewardship essay |
| `runtime_validation` summary | “Persistence bounded”, “Digest silence stable”, “Telemetry canonical” |
| `metrics_json` | Growth rate < 0.5 typical; no `metrics_json_oversize` in validation |
| Degradation mode | `NORMAL` during calm periods |
| Scheduler | No stalled watchdog-eligible loops |
| Governance visibility | Operator sees calm stewardship, not expanding maturity manifesto |
| Convergence | `governance_finalization_candidate` may be true — does **not** mean stop development |

---

## Operational signals (investigate)

| Signal | Action |
|--------|--------|
| `monthly_verdict: surgical_maintenance_required` | Evidence-only fix; no new layers |
| `hidden_entropy_observed` | Review minimalism / calm runtime week |
| `stewardship_recursion_detected` | Review digest sources; do not add meta-layers |
| `telemetry_fragmentation_detected` | Check collector reads post-enrich `gov` |
| Stalled digest scheduler | See emergency section |
| Rising `recovery_activation_count` | Review restart logs and loop errors |

---

## Emergency actions

### Safe restart

1. Note current `STEADY_STATE_STATUS.md` validation date
2. Stop operator process (systemd / compose)
3. Start operator; tail logs 5–10 min
4. Run `python3 scripts/weekly_runtime_validation.py`
5. Update `STEADY_STATE_STATUS.md` if verdict changed

### Degraded-mode verification

1. Check `flow_governance.degradation.mode` via collector or digest
2. Confirm publish path still fail-open (stewardship advisory only)
3. Do not add governance layers — fix root survivability issue if proven

### Scheduler recovery

1. Inspect loop registry: stalled `digest-scheduler` or ingest loops
2. Check `bot/observability/loop_registry.py` snapshot in runtime logs
3. Restart operator if stall persists; record in weekly baseline

### Telemetry sanity

1. `runtime_validation_snapshot(ctx)` → `collector_integrity_ok`
2. Compare `flow_governance` nested vs top-level scalars (propagation signals)
3. Surgical fix in collector only if stale reads confirmed

---

## Documentation hygiene (quarterly, manual)

- [ ] Archive obsolete experimental docs (see freeze doc § historical compression)
- [ ] Do **not** collapse governance code without evidence
- [ ] Keep ADRs as history; point readers to institutional snapshot

---

## Transfer sign-off

| Item | Name | Date |
|------|------|------|
| Incoming steward reviewed snapshot | | |
| Weekly validation run successful | | |
| Monthly review template understood | | |
| Freeze policy acknowledged | | |
| Publish path independence confirmed | | |

---

## Related

- [weekly_operational_baseline.md](weekly_operational_baseline.md)
- [monthly_stability_review.md](monthly_stability_review.md)
- [operational_stability_discipline.md](operational_stability_discipline.md)
