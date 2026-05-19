# Institutional architecture snapshot

**Purpose:** Onboard an engineer without tribal knowledge.  
**Scope:** Mature newsroom steady-state — not a roadmap.

---

## What this system is

A **production-lite Telegram AI newsroom**: ingest → editorial judgment → publish, with **advisory stewardship** that compresses operator noise as the system calms down. Publish path is separate from governance; governance must never block publish.

---

## Governance chain (conceptual)

```
ingest / publish hooks
        ↓
flow_health (cadence, coverage, calibration, adaptive)
        ↓
governance_snapshot()  — baseline bundle
        ↓
collect_operational_context()
        ↓
enrich_governance_with_cockpit(ctx)
        ↓
flatten ctx from enriched gov
        ↓
observability_snapshot()  — cohesion / propagation
        ↓
convergence_snapshot()    — finalization / recursion
        ↓
operator digest (signal_compression)
```

**Maturity progression (advisory bands only):** certification → freeze → memory → doctrine → resilience → minimalism → closure → legacy → observability → convergence.

**End state:** governance describes stability; further layers yield diminishing operational clarity (convergence).

---

## Runtime validation flow

Separate from governance — **infrastructure verification**:

| Step | Action |
|------|--------|
| Weekly | `python3 scripts/weekly_runtime_validation.py --record` |
| Monthly | `python3 scripts/monthly_stability_review.py` |
| On demand | `runtime_validation_snapshot(ctx)` |

Checks: persistence bounds, digest silence, scheduler stalls, telemetry propagation, restart health, operational aging.

History: `var/ops/stability/weekly_baseline.jsonl` (max 90 lines).

---

## Preservation discipline

1. **Stability discipline** — 30–90d observation ([operational_stability_discipline.md](../operations/operational_stability_discipline.md))
2. **Preservation mode** — evidence-gated changes only ([operational_preservation_mode.md](../operations/operational_preservation_mode.md))
3. **Stewardship freeze** — no expansion without defect proof ([governance_surface_freeze.md](governance_surface_freeze.md))

---

## Operational philosophy

| Principle | Practice |
|-----------|----------|
| Calm over novelty | Preserve calmness longer than features |
| Boring infrastructure | Digest invisible; operator interventions rare |
| Advisory stewardship | Describe state; do not orchestrate |
| Bounded memory | `metrics_json` continuity maps capped |
| Fail-open | Stewardship errors are silent to publish |

---

## Boundedness guarantees

- **Persistence:** day-maps trimmed (~40 keys); incidents capped (40); evolution ledger bounded
- **Digest:** early-return quiet modes; max ~4 lines when invisible/finalization quiet
- **Telemetry:** collector reads post-enrich governance; propagation verifies scalar alignment
- **Runtime validation:** read-only inspection; no new persistence from validation itself

---

## Fail-open guarantees

- Each stewardship snapshot wrapped in `try/except` in collector and enrich paths
- `failure_behavior: fail-open` in `contracts.py` for `publish_flow_health`
- Validation scripts exit non-zero on review — they do not stop the bot

---

## Persistence boundaries

| Store | Contents |
|-------|----------|
| `ops_flow_health_state` | `metrics_json` stewardship continuity, baselines, memory |
| `var/ops/stability/` | Weekly validation JSONL (human review) |
| Publish / funnel tables | Operational truth for publishing (unchanged by freeze) |

Do not add unbounded keys to `metrics_json` without explicit retention policy.

---

## Digest silence model

Quietest modes win in `signal_compression.py`:

- **Invisible digest** (minimalism + long-horizon calm)
- **Ultra-quiet** (freeze registry stewardship horizon)
- **Finalization quiet** (convergence candidate + observability canonical)
- **Succession / closure** single-line returns

Verbosity is a **regression**, not a feature.

---

## Maintenance doctrine

1. Observe (weekly + monthly scripts)
2. Record evidence in baseline templates
3. Change only if boundedness or survivability breaks
4. Prefer surgical fix over new abstraction
5. Update [STEADY_STATE_STATUS.md](../operations/STEADY_STATE_STATUS.md) after significant validation

---

## Key paths (quick reference)

| Area | Path |
|------|------|
| Governance hub | `bot/editorial/flow_health/governance.py` |
| Collector | `bot/operator_ux/collector.py` |
| Digest compression | `bot/editorial/flow_health/signal_compression.py` |
| State | `bot/editorial/flow_health/state.py` |
| Runtime validation | `bot/editorial/runtime_validation/` |
| Contracts | `bot/ops_consolidation/contracts.py` |
| Publish flow | `bot/editorial/publish_flow.py` (frozen — no stewardship imports) |

---

## Related

- [governance_surface_freeze.md](governance_surface_freeze.md)
- [../operations/stewardship_transfer_checklist.md](../operations/stewardship_transfer_checklist.md)
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) (broader system context)
