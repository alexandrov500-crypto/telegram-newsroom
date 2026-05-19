# Infrastructure custodianship

**Mode:** Long-term custodianship — not development, not optimization.

Philosophy: *A mature infrastructure eventually transitions from active stewardship to quiet custodianship.*

Prerequisites: [engineering_restraint_charter.md](engineering_restraint_charter.md) · [stewardship_dormancy.md](stewardship_dormancy.md) · [governance_surface_freeze.md](../architecture/governance_surface_freeze.md) · [operational_time_capsule.md](../architecture/operational_time_capsule.md)

---

## Custodian vs architect

| Role | Phase | Mindset |
|------|-------|---------|
| **Architect** | Expansion (closed) | Add clarity, layers, structure |
| **Custodian** | Hibernation readiness | Preserve calm, intervene rarely |

**Expansion phase is complete.** Engineering value is preservation, not novelty.

---

## Custodian responsibilities

| Cadence | Action |
|---------|--------|
| Weekly | `python3 scripts/weekly_runtime_validation.py --record` |
| Weekly | [weekly_calmness_check.md](weekly_calmness_check.md) + [weekly_non_intervention_log.md](weekly_non_intervention_log.md) |
| Monthly | `python3 scripts/monthly_stability_review.py` → [monthly_stability_review.md](monthly_stability_review.md) |
| On restart | Validation script + log review; update [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md) |
| Ongoing | Observe `metrics_json` boundedness (no proactive trimming without evidence) |
| Emergency | Survivability / security repair only — surgical, bounded, reversible |

Handoff reference: [stewardship_transfer_checklist.md](stewardship_transfer_checklist.md).

---

## Custodian non-responsibilities

Do **not** treat as custodian work:

- Feature expansion
- Maturity or governance layer additions
- Governance “refinement” or observability growth
- Optimization without measured degradation
- Cleanup campaigns without evidence
- Architecture modernization or elegance refactors
- New operational rituals or tooling ecosystems

If tempted — read [hibernation_readiness.md](hibernation_readiness.md) and apply intervention scarcity below.

---

## Intervention scarcity

**Intervention requires stronger evidence than preservation.**

Every change needs:

- operational evidence (not curiosity)
- bounded scope
- survivability justification
- measurable necessity

If the system can continue calmly unchanged — **preserve**.

Policy detail: [operational_preservation_mode.md](operational_preservation_mode.md) · [quiet_operations_continuity.md](quiet_operations_continuity.md).

---

## Long-horizon observation (6–12 months)

Do **not** maintain “development momentum.”

**Healthy:**

- empty maintenance weeks
- no incidents
- quiet logs
- stable validation summaries
- invisible digest
- no architectural commits

**Engineering inactivity with calm runtime = success.**

Track optional hibernation streak in [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md).

---

## Related

- [hibernation_readiness.md](hibernation_readiness.md)
- [institutional_architecture_snapshot.md](../architecture/institutional_architecture_snapshot.md)
