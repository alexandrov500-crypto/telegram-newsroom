# v3.2 transition notice

> **Historical (superseded):** Issued at stewardship transition (`v3.2-operational-tooling-freeze`).  
> **Current mode:** **DORMANT** preservation-only — [repository_preservation_notice.md](repository_preservation_notice.md) · [terminal_governance_closure.md](terminal_governance_closure.md) · ADR-038.

**Effective:** upon tag `v3.2-operational-tooling-freeze` (historical record)

## Status change

| Phase | State |
|-------|-------|
| v3.2 implementation (P1–P4 + FINAL) | **Complete** |
| Stewardship (at freeze) | **Active** *(superseded: closed → dormant)* |
| Runtime (production-lite) | **Stable** (separate freeze) |

## What this means

1. **Implementation phase complete** — no new tooling subsystems planned under v3.2.
2. **Stewardship phase active** — bugfixes, docs, additive schema only.
3. **Runtime intentionally stable** — tooling releases do not imply runtime releases.
4. **Tooling intentionally bounded** — offline files under `var/ops_*` only.
5. **Future work requires governance review** — ADR-035+ for scope expansion.
6. **No platformization planned** — no ops SaaS, no live telemetry stack.

## For operators

Continue production-lite runbooks unchanged. Use ops tooling for **offline** shift handoff and incident context — not for live control.

## For engineers

Default gate: `make stewardship-validate`. Read [MAINTAINERS_GUIDE.md](../MAINTAINERS_GUIDE.md) before any `tools/ops_*` change.

## Questions

| Topic | Document |
|-------|----------|
| What shipped? | [v3_2_release_publication.md](v3_2_release_publication.md) |
| What is frozen? | [v3_2_immutable_baseline.md](v3_2_immutable_baseline.md) |
| How to maintain? | [long_term_stewardship.md](../governance/long_term_stewardship.md) |
