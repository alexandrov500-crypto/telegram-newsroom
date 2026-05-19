# Governance surface freeze

**Status:** Infrastructure Stewardship Freeze — active  
**Intent:** Preserve mature operational infrastructure without architectural expansion.

Philosophy: *A mature infrastructure should eventually become quiet enough to preserve itself through discipline rather than expansion.*

---

## Frozen core (do not redesign)

### Governance chain

Snapshot-time, advisory-only layers under `bot/editorial/flow_health/`:

1. Baseline calibration governance (`governance_snapshot` / `enrich_governance_with_cockpit`)
2. Certification
3. Freeze registry
4. Operational memory
5. Doctrine
6. Strategic resilience
7. Minimalism
8. Closure
9. Legacy
10. Observability (cohesion / propagation verification)
11. Convergence (finalization / recursion awareness)

**Hub:** `bot/editorial/flow_health/governance.py`  
**Contracts:** `bot/ops_consolidation/contracts.py` → `publish_flow_health`

### Collector propagation model

1. `collect_operational_context()` loads flow health
2. `enrich_governance_with_cockpit(ctx)` builds canonical `flow_governance`
3. Top-level `ctx` fields flattened from **post-enrich** `gov` (not pre-enrich copy)
4. `observability_snapshot()` then `convergence_snapshot()` attach to `gov` and `ctx`

**File:** `bot/operator_ux/collector.py`

### Digest priority ordering

`format_compressed_digest_html()` early returns (first match wins):

1. Convergence finalization quiet
2. Convergence recursion advisory
3. Observability canonical quiet
4. Observability drift advisory
5. Legacy succession
6. Closure candidate
7. …expanded stewardship only when not calm

**File:** `bot/editorial/flow_health/signal_compression.py`

### Runtime validation tooling (frozen interface)

On-demand only — **not** a governance layer:

- `bot/editorial/runtime_validation/` — snapshot verification
- `scripts/weekly_runtime_validation.py` — weekly baseline JSONL
- `scripts/monthly_stability_review.py` — monthly verdict

### Bounded persistence policy

- Store: `ops_flow_health_state.metrics_json`
- API: `bot/editorial/flow_health/state.py` (`load_state` / `save_state`)
- Continuity keys capped (~40 day-maps): observability, convergence, closure, minimalism, legacy, doctrine, etc.
- Validation limits: `runtime_validation/persistence.py` (256KB metrics_json guideline)

### Advisory-only guarantees

| Guarantee | Meaning |
|-----------|---------|
| Fail-open | Exceptions do not block publish |
| Snapshot-only | No background reconciliation loops in stewardship layers |
| No publish mutation | Stewardship does not change publish verdicts |
| Bounded writes | Continuity / memory structures trimmed on touch |
| Digest compression | Quieter digest as maturity increases |

---

## Allowed maintenance

Changes permitted **only with operational evidence** (see [operational_preservation_mode.md](../operations/operational_preservation_mode.md)):

- Bug fixes affecting survivability
- Scheduler hardening / restart recovery
- Bounded `metrics_json` cleanup or trim
- Stale top-level telemetry null fixes
- Digest line reduction when noise drift proven
- Collector propagation corrections
- Dead-path removal after manual review (`identify_dead_complexity_signals`)

---

## Forbidden expansion

Do **not** add without passing the 6-question minimalism filter and explicit evidence:

- New maturity abstractions or governance layers
- Recursive governance / meta-stewardship
- Orchestration engines or event-bus sync
- Adaptive / self-modifying governance
- Telemetry platformization or dashboards
- AI introspection / semantic operational reasoning
- Autonomous cleanup or self-healing loops
- Architecture modernization “for elegance”

---

## Historical compression (archive discipline only)

Permitted **documentation** cleanup — not codebase redesign:

| May archive / consolidate | Must not |
|---------------------------|----------|
| Obsolete experimental docs | Collapse live governance chain |
| Abandoned design notes | Aggressive code pruning |
| Duplicate governance descriptions | Remove bounded persistence |
| Stale migration drafts | Rewrite stewardship for “simplicity” |

Prefer: mark superseded ADRs as historical, link to [institutional_architecture_snapshot.md](institutional_architecture_snapshot.md).

---

## Related documents

- [operational_time_capsule.md](operational_time_capsule.md)
- [../operations/infrastructure_custodianship.md](../operations/infrastructure_custodianship.md)
- [../operations/hibernation_readiness.md](../operations/hibernation_readiness.md)
- [../operations/quiet_operations_continuity.md](../operations/quiet_operations_continuity.md)
- [institutional_architecture_snapshot.md](institutional_architecture_snapshot.md)
- [../operations/STEADY_STATE_STATUS.md](../operations/STEADY_STATE_STATUS.md)
- [../operations/stewardship_transfer_checklist.md](../operations/stewardship_transfer_checklist.md)
- [../operations/operational_preservation_mode.md](../operations/operational_preservation_mode.md)
