# Maintenance thresholds

**Purpose:** Classify interventions during passive continuity — not a ticket system, not automation.

Declaration: [PASSIVE_CONTINUITY_DECLARATION.md](PASSIVE_CONTINUITY_DECLARATION.md)

---

## Allowed intervention classes

| Class | Examples | Bar |
|-------|----------|-----|
| **Security fixes** | CVE patches, credential rotation, abuse blocks | Standard security hygiene |
| **Runtime survivability** | Scheduler stall, restart failure, publish path break | Measurable regression |
| **Dependency breakage** | Pin updates when upstream breaks deploy | Reproducible failure |
| **Bounded operational repair** | Collector stale reads, `metrics_json` trim, digest noise | Evidence + bounded diff |
| **Infrastructure compatibility** | OS/runtime minimum for continued operation | External force |

All require: bounded scope, reversibility where possible, architecture preserved.

---

## Non-allowed intervention classes

| Class | Why excluded |
|-------|----------------|
| Architecture refresh | Expansion closed |
| Modernization momentum | Novelty without defect |
| Governance optimization | Chain complete |
| Observability enrichment | Cohesion sufficient |
| Maturity recursion | Sediment risk |
| “Clean rewrite” initiatives | Restlessness |
| Speculative resilience work | No measured risk |
| Optimization for calm systems | Maturity is calm |

If unsure — apply [engineering_restraint_charter.md](engineering_restraint_charter.md): justify why **non-intervention is unsafe**.

---

## Decision shortcut

```
Is there measurable operational evidence?  → no  → do nothing
Is survivability at risk if unchanged?     → no  → do nothing
Is the fix bounded and architecture-preserving? → no  → redesign proposal rejected
```

---

## Related

- [long_horizon_custodian_notes.md](long_horizon_custodian_notes.md)
- [stewardship_sunset_boundary.md](stewardship_sunset_boundary.md)
