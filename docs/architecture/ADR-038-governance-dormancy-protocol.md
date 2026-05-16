# ADR-038: Governance dormancy protocol

**Status:** Accepted (dormancy governance only — **no implementation**)  
**Date:** 2026-05-16  
**Depends on:** ADR-037; tags `v3.2-operational-tooling-freeze`, `v3.2-archival-baseline`

## Decision

The repository enters **governance dormancy**: a preserved, intentionally inactive state where **preservation outweighs activity** and **reactivation is governance-gated only**.

This ADR does not authorize development, tooling growth, or restart. It defines how the repository is **maintained while dormant**.

## Why the repository enters dormancy

1. v3.2 implementation, stewardship build-out, archival certification, and meta-governance (ADR-037) are **complete**.
2. Continued “active stewardship” creates **implicit expectation of future work**.
3. Dormancy makes **inactivity healthy and explicit**.
4. Archival baseline must remain canonical without engineering churn.
5. Exceptional evolution requires [ADR-037](ADR-037-governance-restart-framework.md) — not default continuity.

## Stewardship vs dormancy

| Aspect | Stewardship (closed) | Dormancy (current) |
|--------|----------------------|---------------------|
| Mindset | Active program maintenance | Preserved artifact |
| Cadence | Weekly/monthly ops tasks | Reduced 90d/180d preservation |
| Expectation | May improve tooling | No improvement expected |
| Validation | Full chains on change | Spot-checks; incident-only deep review |
| Roadmap | Implicit risk | **Explicitly none** |
| Restart | Framework exists | **Trigger guide only** |

Stewardship **implementation** is closed; dormancy **preservation** is the ongoing mode.

## Dormant repository philosophy

- The repo is a **bounded archival system**, not a product backlog.
- **Silence is success** — no commits is often correct.
- Changes are **suspicious until classified** as preservation or rejected.
- Operators own **integrity**, not **velocity**.

## Preservation-over-activity principle

When choosing between:

- Regenerating a seal vs adding a feature → seal
- Updating a doc link vs new tool → link (if broken)
- Running quarterly check vs refactoring → check
- Doing nothing vs “small cleanup” → **nothing** (default)

## Governance-triggered reactivation only

Exit dormancy requires:

1. [dormancy_reactivation_trigger_guide.md](../runbooks/dormancy_reactivation_trigger_guide.md) criteria
2. Completed [restart_evaluation_template.md](../governance/restart_evaluation_template.md)
3. [governance_restart_review.md](../runbooks/governance_restart_review.md) outcome
4. **Explicit approval** — not ADR-038 alone

## Dormancy allows

| Activity | Reference |
|----------|-----------|
| Archival preservation | [dormancy_operations_policy.md](../governance/dormancy_operations_policy.md) |
| Integrity verification | `check_freeze_integrity.py`, seals (existing) |
| Security-critical hotfix **review** | [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md) |
| Deterministic recovery verification | [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md) (180d) |

## Dormancy forbids

| Activity | Rationale |
|----------|-----------|
| Active roadmap planning | Implicit continuation |
| Opportunistic improvements | Scope accumulation |
| Tooling growth | ADR-034/036 freeze |
| Observability expansion | Platform creep |
| Architecture evolution | Requires restart program |
| Platform ambitions | Terminal state |

## References

- [governance_suspension_matrix.md](../governance/governance_suspension_matrix.md)
- [final_dormancy_declaration.md](../releases/final_dormancy_declaration.md)
- [terminal_governance_closure.md](../releases/terminal_governance_closure.md)
