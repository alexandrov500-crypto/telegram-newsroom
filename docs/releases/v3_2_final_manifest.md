# v3.2 final manifest

Formal inventory for the **completed v3.2 operational tooling program**.

## Program status

| Phase | Status | Exit doc |
|-------|--------|----------|
| Planning | Complete | [v3_2_planning_gate.md](v3_2_planning_gate.md) |
| P1 Tooling | Complete | [v3_2_p1_exit_criteria.md](v3_2_p1_exit_criteria.md) |
| P2 Analytics | Complete | [v3_2_p2_exit_criteria.md](v3_2_p2_exit_criteria.md) |
| P3 Governance | Complete | [v3_2_p3_exit_criteria.md](v3_2_p3_exit_criteria.md) |
| P4 Packaging | Complete | [v3_2_tooling_freeze.md](v3_2_tooling_freeze.md) |
| FINAL Stewardship | Complete | [v3_2_stewardship_handoff.md](v3_2_stewardship_handoff.md) |

## ADR inventory (v3.2)

| ADR | Title |
|-----|-------|
| ADR-030 | Operational tooling scope (P1) |
| ADR-031 | Operational analytics layer (P2) |
| ADR-032 | Operational schema governance (P3) |
| ADR-033 | Operational packaging and maintenance (P4) |
| ADR-034 | v3.2 finalization and stewardship (FINAL) |

## Tooling inventory

| Tool | Phase | Purpose |
|------|-------|---------|
| `ops_metrics_snapshot.py` | P1 | Capture read-only metrics snapshot |
| `queue_introspection.py` | P1 | Read-only Redis queue inspect |
| `publish_timeline_report.py` | P1 | Publish timeline from snapshots |
| `ops_analytics_aggregate.py` | P2 | Offline analytics JSON/MD |
| `ops_visualize.py` | P2 | Static SVG charts |
| `ops_archive.py` | P2 | Gzip archive + verify |
| `generate_shift_handoff.py` | P2 | Shift handoff markdown |
| `validate_ops_schema.py` | P3 | Schema + archive validation |
| `export_ops_bundle.py` | P3 | Reproducible bundle export |
| `generate_ops_html_report.py` | P3 | Single-file HTML report |
| `build_ops_release_kit.py` | P4 | Portable release kit |
| `generate_ops_index.py` | P4 | Static ops index HTML |
| `live_telegram_diagnostics.py` | v3 | Read-only diagnostics source (embedded in snapshots) |

## Utils inventory

| Module | Purpose |
|--------|---------|
| `utils/ops_tooling.py` | Snapshots, rotation, validation |
| `utils/ops_analytics.py` | Trends, SVG, archive, handoff |
| `utils/ops_schema_governance.py` | Schema validation reports |
| `utils/ops_bundle.py` | Bundle + HTML report builder |
| `utils/ops_release_kit.py` | Release kit assembly + verify |
| `utils/ops_index.py` | Static index HTML |
| `utils/queue_introspection.py` | Read-only queue helpers |

## Validation targets

| Make target | Scope |
|-------------|-------|
| `ops-tooling-validate` | P1 |
| `ops-analytics-validate` | P2 |
| `ops-bundle-validate` | P3 |
| `ops-release-validate` | P4 + integration |
| `stewardship-validate` | FINAL (all ops + normalization) |

## Report / artifact inventory

| Path | Regenerable | Gitignored |
|------|-------------|------------|
| `var/ops_history/` | Via snapshot tool | Yes |
| `var/ops_reports/` | Yes | Yes |
| `var/ops_archive/` | Via archive tool | Yes |
| `var/ops_bundle/` | Yes | Yes |
| `var/ops_release_kit/` | Yes | Yes |

## Governance inventory

- [operational_tooling_maintenance_policy.md](../governance/operational_tooling_maintenance_policy.md)
- [long_term_stewardship.md](../governance/long_term_stewardship.md)
- [operational_integrity_audit.md](../operations/operational_integrity_audit.md)
- [metrics_retention_policy.md](../operations/metrics_retention_policy.md)
- [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md)
- [offline_recovery_certification.md](offline_recovery_certification.md)
- [operational_maturity_assessment.md](operational_maturity_assessment.md)
- [repository_normalization_report.md](../repository/repository_normalization_report.md)

## Release tags

| Tag | Purpose |
|-----|---------|
| `v3.1-production-lite` | Production-lite runtime activation (separate) |
| `v3.2-operational-tooling-freeze` | Offline tooling stewardship baseline |

## Commit references (tooling program)

| Phase | Commit (short) | Message |
|-------|----------------|---------|
| P1 | `876e1b9` | feat(v3.2): P1 read-only operational tooling (ADR-030) |
| P2 | `963bdf0` | feat(v3.2): P2 offline operational analytics layer (ADR-031) |
| P3–P4 + FINAL | `ab7c92a` | feat(v3.2): finalize operational tooling stewardship baseline |
| **Freeze tag** | `v3.2-operational-tooling-freeze` | → `ab7c92a` |

> After merge, record the single consolidation commit SHA here and on the annotated tag.

## Operational guarantees

1. Tooling is **read-only** with respect to Telegram and Redis mutation paths.
2. Outputs are **deterministic** under fixed `OPS_FROZEN_UTC` and fixture inputs.
3. Storage is **bounded** per retention policy and kit caps.
4. Corrupt inputs are **isolated**, not fatal to batch processing.
5. Production-lite **runtime semantics unchanged** by this program.

## Explicit non-goals

- Monitoring platform or APM
- Live dashboards and WebSocket feeds
- Autonomous remediation
- Runtime contract changes
- Multi-tenant ops SaaS
