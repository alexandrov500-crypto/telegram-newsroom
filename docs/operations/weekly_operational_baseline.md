# Weekly operational baseline

Manual stability record. **Not a dashboard.** Copy from `scripts/weekly_runtime_validation.py --record` or fill by hand.

## Week metadata

| Field | Value |
|-------|-------|
| Week ID | e.g. `2026-W20` |
| Recorded (UTC) | |
| Reviewer | |
| Environment | production-lite / staging |

## Runtime

| Metric | This week | Prior week | Notes |
|--------|-----------|------------|-------|
| Restart count (`recovery_activation_count`) | | | |
| Recovery active | | | |
| Scheduler stability (0–1) | | | |
| Stalled loops | | | |
| Publish continuity OK | | | |
| Degradation mode | | | |
| Degraded recovery score | | | |

## Persistence

| Metric | This week | Prior week | Notes |
|--------|-----------|------------|-------|
| metrics_json bytes | | | |
| persistence_growth_rate | | | target < 0.85 |
| continuity_storage_pressure | | | target < 0.9 |
| memory_retention_health | | | |
| bounded_persistence_ok | | | |

## Digest

| Metric | This week | Prior week | Notes |
|--------|-----------|------------|-------|
| digest_line_count | | | quiet: ≤ 4 |
| digest_noise_drift | | | target < 0.25 |
| invisible_digest (Y/N) | | | |
| ultra_quiet (Y/N) | | | |
| finalization_quiet (Y/N) | | | |
| stewardship_verbosity_pressure | | | |

## Telemetry

| Metric | This week | Prior week | Notes |
|--------|-----------|------------|-------|
| collector_integrity_ok | | | |
| canonical_telemetry_stability | | | |
| telemetry_fragmentation_detected | | | |
| telemetry_growth_rate | | | |

## Operational calmness

| Metric | This week | Prior week | Notes |
|--------|-----------|------------|-------|
| infrastructure_validation_ok | | | |
| checks passed / total | | | |
| hidden_entropy_observed | | | |
| operational_aging_ok | | | |
| long_horizon_calm | | | |
| operational_fatigue_detected | | | |

## Validation summary (paste)

```
(paste report summary_lines here)
```

## Evidence for changes this week

| Change made? | Evidence link / metric | Approved? |
|--------------|------------------------|-----------|
| None | — | — |

## Expansion proposals (if any)

| Proposal | Defect | Boundedness violation | Missing signal | Why existing layers fail | Recursion risk | Decision |
|----------|--------|----------------------|----------------|------------------------|----------------|----------|
| | | | | | | defer / reject / accept |

## Weekly judgment

- [ ] Calm — no action
- [ ] Watch — observe another week
- [ ] Maintain — evidence-driven surgical fix only

**One-line summary:**
