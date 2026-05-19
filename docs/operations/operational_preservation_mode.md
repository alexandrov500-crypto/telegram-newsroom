# Operational Preservation Mode

**Preserve calmness. Resist curiosity-driven expansion.**

Philosophy: *A mature infrastructure should resist unnecessary improvement as carefully as it resists instability.*

Supersedes expansion mindset. Complements [operational_stability_discipline.md](operational_stability_discipline.md).

---

## Preservation discipline (all changes)

Every change requires **observable evidence**:

- boundedness violation
- survivability regression
- runtime instability
- persistence drift
- telemetry fragmentation
- digest noise growth

**Insufficient reasons:** prettier, smarter, cleaner, more modern.

---

## Weekly → monthly rhythm

| Cadence | Tool | Purpose |
|---------|------|---------|
| Weekly | `scripts/weekly_runtime_validation.py --record` | Snapshot + JSONL |
| Monthly | `scripts/monthly_stability_review.py` | Drift + verdict |

```bash
python3 scripts/monthly_stability_review.py
python3 scripts/monthly_stability_review.py --json
```

**Monthly verdicts:**

- `stable` — no action
- `observe` — continue watching, no architecture work
- `surgical_maintenance_required` — evidence-backed fixes only

Copy results into [monthly_stability_review.md](monthly_stability_review.md).

---

## Surgical maintenance (when evidence exists)

| Allowed | Forbidden |
|---------|-----------|
| bounded cleanup | governance redesign |
| stale telemetry removal | architecture rewrite |
| persistence trimming | new maturity models |
| dead-path deletion (manual) | platformization |
| coupling reduction | orchestration |
| digest simplification | recursive stewardship |
| scheduler hardening | auto-removal bots |

---

## Dead complexity detection

`identify_dead_complexity_signals()` — **hints only**, no auto-removal.

Engineering reviews hints manually. Examples: empty continuity keys, permanent digest silence, null flow telemetry.

---

## Operational minimalism filter (new ideas)

1. What real operational defect exists?
2. Why is current governance insufficient?
3. Is there measurable evidence?
4. Why can't the fix be surgical?
5. Does it create new stewardship surface?
6. Does it violate boring-infrastructure discipline?

Weak answers → **do not implement**.

---

## Long-horizon KPI (60–90 days)

Success = preservation of calmness, not feature growth:

- digest quiet / invisible
- persistence growth near-flat
- rare scheduler interruptions
- boring restart survivability
- canonical telemetry
- rare operator interventions
- stable `runtime_validation`
- **no** pressure for new governance layers

---

## Hard constraints

**Forbidden:** new maturity frameworks, recursive observability, AI introspection, orchestration, telemetry ecosystems, adaptive infrastructure, autonomous maintenance, governance self-improvement.

**Allowed:** preservation, bounded maintenance, survivability fixes, runtime verification, evidence-driven manual cleanup.

---

## Stewardship freeze

Architecture and governance surface are frozen — see [governance_surface_freeze.md](../architecture/governance_surface_freeze.md) and update [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md) after validation.

## Quiet operations

After preservation discipline is routine, operate in **patience mode**: [quiet_operations_continuity.md](quiet_operations_continuity.md) · weekly [weekly_calmness_check.md](weekly_calmness_check.md).

## Dormancy

Default stance: **safely untouched** unless evidence compels action — [stewardship_dormancy.md](stewardship_dormancy.md).

## Related

- [weekly_operational_baseline.md](weekly_operational_baseline.md)
- [monthly_stability_review.md](monthly_stability_review.md)
- [stewardship_transfer_checklist.md](stewardship_transfer_checklist.md)
- `bot/editorial/runtime_validation/preservation.py`
