# Operational time capsule

Compact record for future custodians. **Timeless intent** — not an implementation manual.

Full reference when needed: [institutional_architecture_snapshot.md](institutional_architecture_snapshot.md).

---

## Final architectural philosophy

- **Publish path is sacred** — stewardship never blocks ingest/publish.
- **Advisory-only** — governance describes; it does not orchestrate.
- **Fail-open** — stewardship errors are silent to operations.
- **Calm over novelty** — quieter digest as maturity increases.
- **Bounded memory** — `metrics_json` continuity maps do not grow without limit.
- **Boring is success** — stable weeks without engineering change are healthy.

---

## Governance boundaries (frozen)

Stewardship chain is **complete** and **frozen**:

certification → freeze_registry → operational_memory → doctrine → strategic_resilience → minimalism → closure → legacy → observability → convergence

**Do not extend** without defect evidence and [governance_surface_freeze.md](governance_surface_freeze.md) gate.

Runtime validation (`bot/editorial/runtime_validation/`) verifies infrastructure — it is **not** another maturity layer.

---

## Why expansion stopped

1. Governance reached **explanatory completeness** (convergence / finalization awareness).
2. Further layers produced **diminishing operational clarity** (recursion risk).
3. Main risk shifted from instability to **fragmentation, sediment, and curiosity-driven churn**.
4. Mature newsroom should **preserve calmness** longer than novelty.

---

## Must remain untouched (without evidence)

- Publish pipeline semantics and guard model
- Governance chain ordering and advisory-only contract
- Collector **post-enrich** canonical propagation model
- Digest priority ordering (convergence → observability → legacy → closure → …)
- Bounded persistence keys and retention caps
- Freeze / preservation / dormancy **policy** (docs, not code churn)

---

## Signals that justify intervention

| Signal | Example action |
|--------|----------------|
| Boundedness violation | Surgical `metrics_json` trim |
| Survivability regression | Scheduler / restart fix |
| Telemetry fragmentation | Collector propagation fix |
| Digest noise drift | Signal compression adjustment |
| Security / abuse | Patch outside governance chain |
| Emergency outage | Restore service; document in baseline |

**Not justified:** elegance, smarter governance, new maturity abstractions, cleanup without measurement.

**Bar:** intervention evidence must be **stronger** than preservation — see [infrastructure_custodianship.md](../operations/infrastructure_custodianship.md).

---

## Custodianship handoff

1. Read this capsule  
2. [infrastructure_custodianship.md](../operations/infrastructure_custodianship.md)  
3. [hibernation_readiness.md](../operations/hibernation_readiness.md)  
4. [STEADY_STATE_STATUS.md](../operations/STEADY_STATE_STATUS.md)  
5. [engineering_restraint_charter.md](../operations/engineering_restraint_charter.md)  
6. [TERMINAL_STEWARDSHIP_NOTE.md](../operations/TERMINAL_STEWARDSHIP_NOTE.md)  

---

## Completion

Architecture is **operationally complete** — see [ARCHITECTURAL_COMPLETION.md](ARCHITECTURAL_COMPLETION.md) and [continuity_covenant.md](../operations/continuity_covenant.md).

Finalization record: [INFRASTRUCTURE_FINALIZATION_RECORD.md](INFRASTRUCTURE_FINALIZATION_RECORD.md) · sunset: [stewardship_sunset_boundary.md](../operations/stewardship_sunset_boundary.md).

## Institutional permanence

The newsroom is intended to **survive through continuity**, not through continuous redesign.

Long periods without architectural change are **success**, not neglect. Custodians preserve legibility and boundedness; they do not hunt for the next maturity layer.

## Philosophy

*A mature infrastructure eventually transitions from active stewardship to quiet custodianship.*

*A completed infrastructure is not one that cannot evolve, but one that no longer needs to.*

*The ultimate success of mature infrastructure is the ability to remain quietly valuable without needing to reinvent itself.*

Date capsule aligned with steady-state freeze: **2026** — update only if operational truth materially changes (rare).
