# Stewardship dormancy & non-intervention discipline

**Mode:** Disciplined dormancy — not continuous improvement.

Philosophy: *A truly mature infrastructure is one that can safely remain untouched.*

Live newsroom operations complement [quiet_operations_continuity.md](quiet_operations_continuity.md). Repository-level dormancy: [ADR-038](../architecture/ADR-038-governance-dormancy-protocol.md).

---

## Mindset shift

| From | To |
|------|-----|
| Continuous improvement | Disciplined dormancy |
| Engineering activity = progress | **Non-intervention** = healthy |
| Optimization | Preservation |
| Innovation pressure | Calm continuity |

**Primary engineering skill:** knowing when **not** to act.

---

## Phase 1 — Non-intervention validation (weekly)

Record what **did not** require change — see [weekly_non_intervention_log.md](weekly_non_intervention_log.md).

**Weekly success** = all true:

- No architectural changes
- No governance / stewardship chain edits
- No persistence pressure (`bounded_persistence_ok`)
- No digest drift
- No telemetry fragmentation
- No operator escalation

**Positive signal:** *system remained safely untouched.*

---

## Phase 2 — Dormancy discipline (before any change)

1. What is **broken** operationally?
2. Is there **measurable evidence**?
3. Is there **risk if unchanged**?
4. Is there a **bounded** fix (surgical, reversible)?
5. Can the newsroom **continue calmly without intervention**?

If **(5) = yes** → **do not change.**

Also apply patience filter in [quiet_operations_continuity.md](quiet_operations_continuity.md) and evidence rules in [operational_preservation_mode.md](operational_preservation_mode.md).

---

## Phase 3 — Silence preservation (healthy signals)

| Healthy | Unhealthy |
|---------|-----------|
| Quiet digest | Regular governance tweaks |
| Boring logs | Architecture churn |
| Predictable runtime | Maintenance for activity’s sake |
| Empty maintenance weeks | “Improvements” without defect |
| Stable validation summaries | New rituals / tooling |
| Low intervention frequency | Optimization without degradation |

---

## Phase 4 — Historical stability (90+ days)

Dormancy maturity when:

- [ ] Architecture remained stable (freeze held)
- [ ] Bounded persistence preserved
- [ ] Calm operations preserved
- [ ] Transferability intact
- [ ] No governance sediment
- [ ] No expansion pressure
- [ ] No engineering restlessness

Document one paragraph in [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md).

---

## Phase 5 — Stewardship restraint

Engineering responsibility is **not** “add value through expansion.”

It is: **do not destroy mature calmness through unnecessary intervention.**

Allowed without dormancy breach:

- Survivability fixes (evidence)
- Security fixes
- Bounded operational repair
- Brief documentation freshness
- Emergency intervention

---

## Hard constraints

**Forbidden:** governance revival, observability expansion, modernization, orchestration, AI ops, recursive maintenance layers, cleanup campaigns without evidence, optimization without degradation proof.

**Permitted:** continuity, bounded repair, validation observation, emergency response.

---

## Expected outcome

A successful system:

- changes rarely
- needs attention rarely
- incidents rare
- stays readable and transferable
- stays calm
- **survives time without engineering pressure**

---

## Custodianship

Long-term mode after dormancy: [infrastructure_custodianship.md](infrastructure_custodianship.md) · readiness [hibernation_readiness.md](hibernation_readiness.md) · [operational_time_capsule.md](../architecture/operational_time_capsule.md).

## Related

- [weekly_non_intervention_log.md](weekly_non_intervention_log.md)
- [weekly_calmness_check.md](weekly_calmness_check.md)
- [governance_surface_freeze.md](../architecture/governance_surface_freeze.md)
