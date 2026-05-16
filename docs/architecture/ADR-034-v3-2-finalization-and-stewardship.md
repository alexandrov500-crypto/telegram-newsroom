# ADR-034: v3.2 finalization and long-term stewardship

**Status:** Accepted  
**Date:** 2026-05-16  
**Depends on:** ADR-030–033 (v3.2 operational tooling program)

## Decision

**Close the v3.2 implementation cycle** and enter **stable stewardship mode** for the offline operational tooling layer. No further tooling subsystems, platform features, or runtime observability coupling without a new ADR program.

## Why tooling scope is now frozen

1. P1–P4 deliverables meet production-lite operator needs (snapshots, analytics, governance, release kits).
2. Further expansion risks platform creep (dashboards, telemetry pipelines, automation).
3. Runtime contracts and publish semantics remain intentionally frozen separately (ADR-015).
4. CI gates (`ops-release-validate`, `stewardship-validate`) provide reproducible verification without new code paths.

## Permanent runtime / tooling separation

| Layer | Location | Mutates runtime? | Network? |
|-------|----------|------------------|----------|
| Production-lite runtime | `app/`, `publisher/`, `collector/`, frozen `runtime/*.json` | Yes (when running) | Yes (Telegram/Redis) |
| Offline ops tooling | `tools/ops_*`, `utils/ops_*`, `var/ops_*` | **Never** | **No** (by design) |

Tooling may **read** diagnostics shape compatible with live collectors; it must not **write** queue state, publish, or schedule work.

## Stewardship philosophy

- **Bounded:** fixed storage caps, deterministic exports, schema versioning.
- **Reproducible:** `OPS_FROZEN_UTC` in CI; manifest + checksums on every kit.
- **Recoverable:** offline drill documented; no SaaS dependency.
- **Auditable:** ADRs, integrity audit, certification checklist.
- **Maintenance-first:** bugfixes and docs; not feature expansion.

## Maintenance boundaries

See [long_term_stewardship.md](../governance/long_term_stewardship.md) and [operational_tooling_maintenance_policy.md](../governance/operational_tooling_maintenance_policy.md).

## Allowed future work

| Category | Examples |
|----------|----------|
| Bounded bugfixes | corrupt snapshot edge case, SVG label fix |
| Schema-compatible improvements | additive JSON fields + ADR note |
| Deterministic tooling maintenance | hash algorithm docs, test fixtures |
| Documentation | runbooks, certification refresh |
| Security fixes | dependency pins, secret hygiene in docs |

## Forbidden future expansion paths

| Anti-pattern | Rationale |
|--------------|-----------|
| Runtime observability coupling | Violates isolation guarantee |
| Live telemetry infrastructure | Network + operational risk |
| Autonomous remediation | No closed-loop control |
| Distributed orchestration | ADR-003 non-goals |
| Analytics feedback loops into publisher | Runtime mutation |
| Platformization (SaaS, multi-tenant ops UI) | Out of project scope |
| Hosted dashboards / CDN assets | Offline portability rule |
| Persistent analytics databases | Bounded `var/` only |

## New work requires new ADR cycle

Any proposal that adds tools, services, runtime hooks, or expands `var/` semantics beyond ADR-030–033 must:

1. Open a new ADR (035+) with explicit non-goals review.
2. Pass `make stewardship-validate` on the branch.
3. Obtain operator sign-off on [v3_2_tooling_freeze.md](../releases/v3_2_tooling_freeze.md) exception process.

## CI and release

- `make stewardship-validate` — final gate for tooling stewardship
- Tag: `v3.2-operational-tooling-freeze` (annotated; see [v3_2_stewardship_handoff.md](../releases/v3_2_stewardship_handoff.md))

## References

- [v3_2_final_manifest.md](../releases/v3_2_final_manifest.md)
- [offline_recovery_certification.md](../releases/offline_recovery_certification.md)
- [operational_maturity_assessment.md](../releases/operational_maturity_assessment.md)
- [repository_normalization_report.md](../repository/repository_normalization_report.md)
