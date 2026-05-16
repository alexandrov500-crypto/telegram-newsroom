# Meta-governance closure

Formal closure of the **v3.x lifecycle ecosystem** and opening of **governance-only** restart evaluation (no implementation).

**Date:** 2026-05-16

## Lifecycles closed

| Lifecycle | State | Closure artifact |
|-----------|-------|------------------|
| v3.2 implementation (P1–P4) | Closed | [v3_2_archival_closure_report.md](v3_2_archival_closure_report.md) |
| v3.2 stewardship (active build) | Closed | [stewardship_state_declaration.md](stewardship_state_declaration.md) |
| v3.2 archival | Closed (preservation active) | `v3.2-archival-baseline` |
| Governance-restart **preparation** | Closed | ADR-037 + this document |
| Dormancy transition | Active mode | ADR-038 + [final_dormancy_declaration.md](final_dormancy_declaration.md) |

## What is active now

| Mode | Activity |
|------|----------|
| **Dormancy** | Preservation-only per [dormancy_operations_policy.md](../governance/dormancy_operations_policy.md) |
| Archival preservation | 90d/180d cadence; seals on check |
| Bounded maintenance | Security-critical hotfix review only |
| Restart **evaluation** | Template + review only if proposed (default deny) |

## What is not active

- No development roadmap
- No v4 branch mandate
- No implicit continuation of P1–P4 work
- No new implementation ADR beyond 037 (037 is meta-only)

## Repository intent

This repository is **intentionally preserved** as a **bounded archival system** for:

- Production-lite Telegram newsroom runtime (separately frozen)
- v3.2 offline operational tooling baseline
- Complete governance and certification chain

## Future evolution

Fully **governance-gated** via [ADR-037](../architecture/ADR-037-governance-restart-framework.md):

1. Submit [restart_evaluation_template.md](../governance/restart_evaluation_template.md)
2. Complete [governance_restart_review.md](../runbooks/governance_restart_review.md)
3. Only then draft ADR-038+ (still no code until program approved)

## Canonical tags

| Tag | Role |
|-----|------|
| `v3.2-operational-tooling-freeze` | Tooling immutability |
| `v3.2-archival-baseline` | Archival publication |

## Entry points

- [repository_terminal_state.md](repository_terminal_state.md)
- [restart_readiness_declaration.md](restart_readiness_declaration.md)
- [ADR-037](../architecture/ADR-037-governance-restart-framework.md)

**v3.x implementation lifecycle: formally closed.**
