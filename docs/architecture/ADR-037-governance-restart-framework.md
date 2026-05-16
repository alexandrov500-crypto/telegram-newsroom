# ADR-037: Governance restart framework (meta-level)

**Status:** Accepted (evaluation framework only — **no implementation authorized**)  
**Date:** 2026-05-16  
**Depends on:** ADR-034, ADR-036; tags `v3.2-operational-tooling-freeze`, `v3.2-archival-baseline`

## Context

The v3.2 operational tooling program reached **terminal archival state**:

- Implementation closed (P1–P4 + FINAL)
- Stewardship closed as an active build program
- Archival baseline certified (`v3.2-archival-baseline`)
- Repository declared terminal ([repository_terminal_state.md](../releases/repository_terminal_state.md))

This ADR does **not** approve v4, new tooling, or runtime work. It defines **how to decide** whether a future governance restart should even be discussed.

## Why v3.2 entered terminal archival state

1. Production-lite runtime and offline ops tooling serve distinct lifecycles.
2. Platform creep was an observed risk (dashboards, telemetry, automation).
3. Bounded `var/` artifacts and deterministic exports met operator needs.
4. Further “small improvements” threatened uncontrolled scope accumulation.
5. Archival-grade preservation requires a stable canonical baseline.

## Why restart requires explicit governance

Without a restart framework:

- Curiosity becomes implicit roadmap
- Hotfix culture drifts into feature culture
- Archival tags lose authority
- Runtime and tooling boundaries erode
- Audit trail fragments across undocumented phases

**Default:** repository remains frozen. Restart is an **exception**, not continuity.

## Preservation-first philosophy

1. **Archival integrity** — tags and manifests remain authoritative.
2. **Governance continuity** — ADR chain and validation history preserved.
3. **Runtime stability** — production path unchanged unless separate runtime program.
4. **Reproducibility** — deterministic stewardship artifacts remain valid.
5. **Simplicity** — reject complexity that does not solve demonstrated operational failure.
6. **Evolution last** — new lifecycle only after evidence and review.

## Anti-continuation safeguards

| Safeguard | Mechanism |
|-----------|-----------|
| No implicit roadmap | [meta_governance_closure.md](../releases/meta_governance_closure.md) |
| Restart template required | [restart_evaluation_template.md](../governance/restart_evaluation_template.md) |
| Risk matrix gate | [governance_restart_risk_matrix.md](../governance/governance_restart_risk_matrix.md) |
| Review runbook | [governance_restart_review.md](../runbooks/governance_restart_review.md) |
| Default denial | [restart_readiness_declaration.md](../releases/restart_readiness_declaration.md) |

## Restart MAY be considered only if

All must be argued with evidence (not opinion):

1. **Operational constraints fundamentally changed** — e.g. sustained inability to operate production-lite within frozen contracts.
2. **Telegram platform semantics changed materially** — breaking assumptions in publish/session model documented with vendor evidence.
3. **Archival baseline insufficient** — demonstrated gap that maintenance/hotfix cannot close under [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md).
4. **Security/compliance requirements changed** — external mandate with audit citation.
5. **Maintainability impossible under freeze** — e.g. language/runtime EOL with no compatible path without scope change.

## Restart MUST NOT happen for

| Driver | Rationale |
|--------|-----------|
| Curiosity | Not operational justification |
| “Small improvements” | Scope accumulation |
| Tooling expansion desire | ADR-034/036 forbidden paths |
| Dashboard/platform ambitions | Platformization rejected |
| Architectural perfectionism | No user-facing failure |
| Speculative scaling | v1.8+ already bounded scaling docs |
| Developer convenience | Not operator evidence |
| Competitor feature parity | Non-goal |

## Acceptable outcomes of evaluation

| Outcome | Meaning |
|---------|---------|
| **Reject** | Default; continue stewardship-only |
| **Defer** | Insufficient evidence; re-evaluate after cooling-off |
| **Approve meta-study** | Docs-only spike; no code |
| **Approve new program** | Requires new ADR-038+ chain, new tags, new validation — **not granted by ADR-037** |

ADR-037 alone **never** authorizes implementation.

## References

- [preservation_priority_policy.md](../governance/preservation_priority_policy.md)
- [terminal_state_preservation_addendum.md](../releases/terminal_state_preservation_addendum.md)
- [MAINTAINERS_GUIDE.md](../MAINTAINERS_GUIDE.md)
