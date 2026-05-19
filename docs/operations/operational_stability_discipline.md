# Operational Stability Discipline

Long-horizon observation for a mature newsroom. **Not architecture expansion.**

Philosophy: *A mature newsroom should preserve calmness longer than it preserves novelty.*

## Mode

| Principle | Practice |
|-----------|----------|
| Minimal change | Surgical fixes only with evidence |
| Observation over expansion | Weekly validation, 30–90d window |
| Boring infrastructure | Digest silence, bounded persistence, calm scheduler |
| No new maturity layers | Unless boundedness or survivability regresses |

## Observation cycle (30–90 days)

**Focus signals** (no new subsystems):

- scheduler continuity
- publish continuity
- digest silence
- telemetry boundedness
- persistence boundedness
- restart survivability
- degradation recovery
- operator calmness
- infrastructure predictability

## Weekly runtime validation

Run manually or lightweight cron (no orchestration engine):

```bash
python3 scripts/weekly_runtime_validation.py
python3 scripts/weekly_runtime_validation.py --record
python3 scripts/weekly_runtime_validation.py --history 4
```

Or in-process:

```python
from bot.operator_ux.collector import collect_operational_context
from bot.editorial.runtime_validation import (
    runtime_validation_snapshot,
    capture_operational_baseline,
    append_baseline_record,
)

ctx = collect_operational_context()
report = runtime_validation_snapshot(ctx=ctx)
baseline = capture_operational_baseline(report)
append_baseline_record(baseline)  # optional, bounded JSONL

for line in report["summary_lines"]:
    print(line)
```

Recorded history: `var/ops/stability/weekly_baseline.jsonl` (max 90 lines).

## Weekly baseline document

Copy fields into [weekly_operational_baseline.md](weekly_operational_baseline.md) each week. Do not build a dashboard.

## Evidence-driven maintenance only

Changes are allowed **only** when validation or baseline shows:

- boundedness violation
- persistence growth (`persistence_growth_rate` > 0.85 sustained)
- scheduler instability (`stalled_loops` non-empty)
- restart survivability regression
- telemetry fragmentation
- digest noise drift under invisible mode
- hidden entropy / operational fatigue

**Not allowed** as reasons: elegance, “smarter governance”, new maturity layers without defect.

## Controlled maintenance

| Allowed | Forbidden |
|---------|-----------|
| surgical fixes | architecture rewrites |
| bounded persistence trim | governance redesign |
| telemetry correction | recursive stewardship |
| digest simplification | observability platform creep |
| stale coupling removal | runtime orchestration |

## Operational freeze discipline (expansion proposals)

Before any new governance layer, answer:

1. Which runtime defect is fixed?
2. Which boundedness rule is violated?
3. Which operational signal is missing?
4. Why are existing layers insufficient?
5. Why is this not governance recursion?

Weak answers → **do not implement**.

## Infrastructure calmness (success signs)

- restart is quiet
- digest nearly empty (invisible / finalization quiet)
- scheduler stable, no watchdog stalls
- `metrics_json` growth bounded
- telemetry canonical (`collector_integrity_ok`)
- governance invisible in operator UX
- rare operator interventions
- `infrastructure_validation_ok` stable week over week

## Success criteria (30–90 days)

- runtime calm stable
- persistence bounded
- scheduler healthy
- restart survivability reliable
- digest mostly silent
- telemetry canonical
- governance invisible
- no hidden entropy trend
- decreasing operator intervention
- **no pressure** to add new governance layers

## Preservation mode

When stability discipline is routine, enter [operational_preservation_mode.md](operational_preservation_mode.md) — evidence-gated maintenance and monthly review.

## Quiet continuity

At steady-state, prefer **no change**: [quiet_operations_continuity.md](quiet_operations_continuity.md). A calm week with no architecture touch is success.

## Related

- [weekly_operational_baseline.md](weekly_operational_baseline.md) — weekly table template
- [monthly_stability_review.md](monthly_stability_review.md) — monthly verdict template
- [production_baselines.md](production_baselines.md) — publish/runtime numeric ranges
- [72h_stability_window.md](72h_stability_window.md) — post-activation window (historical)
- `bot/editorial/runtime_validation/` — snapshot verification tooling
