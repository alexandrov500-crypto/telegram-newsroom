# Governance suspension matrix

Lifecycle states for this repository. **Current state: DORMANT.**

## State diagram

```
ACTIVE (historical) → STEWARDSHIP (closed) → DORMANT (current) → REACTIVATION (exceptional)
```

## Matrix

| Dimension | ACTIVE (historical) | STEWARDSHIP (closed) | DORMANT (current) | REACTIVATION (exceptional) |
|-----------|---------------------|----------------------|-------------------|----------------------------|
| **Allowed** | Feature implementation | Bounded hotfixes, kits, audits | Preservation checks, integrity seals, security review | Per ADR-037 approved program only |
| **Forbidden** | — | New subsystems, platform | Roadmap, tooling growth, refactors | Silent scope creep |
| **Cadence** | Sprint/PR flow | 7d–30d calendar | 90d / 180d preservation | Defined in new ADR if ever |
| **Validation** | CI on every PR | `stewardship-*`, `archival-freeze` on change | Spot-check 90d; full on incident | New chain only if approved |
| **Escalation** | Team lead | Stewardship review | Reactivation trigger guide | Governance board |

## ACTIVE (historical)

Pre-v3.2-terminal. Not re-enterable without restart program.

- P1–P4 implementation occurred here
- Closed by [v3_2_archival_closure_report.md](../releases/v3_2_archival_closure_report.md)

## STEWARDSHIP (closed)

Post-P1, pre-dormancy active maintenance mindset.

- Closed by [stewardship_state_declaration.md](../releases/stewardship_state_declaration.md)
- Superseded for **cadence** by dormancy policy, not for hotfix rules

## DORMANT (current)

**Default since ADR-038.**

- See [dormancy_operations_policy.md](dormancy_operations_policy.md)
- [final_dormancy_declaration.md](../releases/final_dormancy_declaration.md)

## REACTIVATION (exceptional)

Not entered unless:

- [dormancy_reactivation_trigger_guide.md](../runbooks/dormancy_reactivation_trigger_guide.md)
- [restart_readiness_declaration.md](../releases/restart_readiness_declaration.md) updated to approved

**No active reactivation as of 2026-05-16.**

## References

- [ADR-038](../architecture/ADR-038-governance-dormancy-protocol.md)
- [terminal_governance_closure.md](../releases/terminal_governance_closure.md)
