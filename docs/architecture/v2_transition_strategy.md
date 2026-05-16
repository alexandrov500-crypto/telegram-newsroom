# v2 transition strategy

**v2 is a governance and compatibility event — not a feature dump.**

This document defines when a future major version may exist. It does **not** implement v2.

## What justifies v2

A v2 major release is justified only when **multiple** of the following are true, with evidence:

1. **Breaking runtime contract** — intentional change to frozen artifact set, schema version, or CLI registry requiring operator migration.
2. **Sustained measured pain** — SQLite, Redis, or single-node limits block documented workload for >6 months despite 1.x mitigations.
3. **Security or compliance** — external requirement that cannot be met with opt-in 1.x controls.
4. **Incompatible dependency** — upstream (Python, Telegram API, OpenAI) forces non-patchable breaking change across core paths.
5. **Operator-approved migration window** — written plan, rollback tested, evidence compatibility preserved or migrated.

## What does NOT justify v2

- Feature backlog length
- “Modern stack” preferences (K8s, Postgres, Kafka)
- Competitor architecture comparisons
- Developer convenience for local dev only
- Hyperscale projections without production metrics
- Refactor for elegance without operational benefit
- Accumulation of opt-in flags (flags are not debt by themselves)

## Major-version gates

Before tagging v2.0.0:

| Gate | Requirement |
|------|-------------|
| ADR | ADR-0xx “v2 scope” accepted; non-goals explicit |
| Contracts | New schema version documented; migration tooling |
| Evidence | Snapshot/restore compatibility matrix published |
| Operators | Upgrade runbooks + rollback drill completed |
| CI | `release-check` equivalent for v2 branch |
| Governance | Deprecation window for 1.x documented ([deprecation_policy.md](../deprecation_policy.md)) |
| Complexity | [complexity_budget.md](complexity_budget.md) review — net burden justified |

## Compatibility expectations

- **1.x patch/minor** — backward compatible; frozen contracts unchanged.
- **v2.0** — may break contracts only with migration path and ADR.
- **Parallel support** — recommend 1.x maintenance window (minimum 6 months) if v2 ships.

## Migration expectations

- Explicit, documented, testable — no silent schema shifts.
- No hybrid unsupported states ([postgresql_evolution_path.md](../scalability/postgresql_evolution_path.md)).
- Operators receive checklist, not framework magic.
- Evidence archives remain readable or conversion tool provided.

## Rollback expectations

- Rollback to 1.x must be defined before v2 cutover.
- Destructive migrations require backup + quiesce documented.
- Feature flags cannot be the only rollback story for schema breaks.

## Operator continuity guarantees

v2 must preserve where possible:

- Shell-first inspection mental model
- `OUTPUT_DIR` / nightly-check workflow (possibly extended, not replaced)
- Deterministic JSON artifacts philosophy
- Read-only diagnostics default
- Explicit unsupported deployment registry

## 3–5 year evolution posture (without v2)

Recommended 1.x stewardship path:

| Year band | Focus |
|-----------|--------|
| Near term | Maintenance, intelligence, scaling discipline |
| Mid term | Measured pain ADRs (DB, workers) — docs + opt-in only |
| Long term | v2 decision review only if gates met |

**Default assumption:** project remains 1.x production-lite with bounded modules unless gates fire.
