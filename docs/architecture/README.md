# Architecture documentation

Concise **engineering intent** and **ADRs** for this repository. New readers: [../START_HERE.md](../START_HERE.md) · Flows: [../ARCHITECTURE_MAP.md](../ARCHITECTURE_MAP.md). Then [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) and [OPERATIONAL_LIFECYCLE.md](OPERATIONAL_LIFECYCLE.md).

**Governance model:** Complete (ADR-001–014). **Stabilization:** [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md), [RUNTIME_MATURITY.md](RUNTIME_MATURITY.md), [ADR-015](ADR-015-runtime-stabilization-and-contract-freeze.md). No further runtime governance layers planned.

## ADR index

| ADR | Topic | Status | Related docs |
|-----|--------|--------|----------------|
| [ADR-001](ADR-001-bounded-runtime-state.md) | Bounded runtime state | Accepted | `RUNTIME_RETENTION.md`, `RUNTIME_ARTIFACTS.md` |
| [ADR-002](ADR-002-static-operational-dashboard.md) | Static operational dashboard | Accepted | `OPERATIONAL_DASHBOARD.md` |
| [ADR-003](ADR-003-no-orchestration-policy.md) | No orchestration / workflow platform | Accepted | `RUNTIME_OPS.md`, `CI_CD.md` |
| [ADR-004](ADR-004-release-qualification-semantics.md) | Release qualification semantics | Accepted | `RELEASE_QUALIFICATION.md` |
| [ADR-005](ADR-005-runtime-retention-strategy.md) | Runtime retention strategy | Accepted | `RUNTIME_RETENTION.md` |
| [ADR-006](ADR-006-runtime-reporting-semantics.md) | Runtime reporting semantics | Accepted | `RUNTIME_OPS.md`, `observability/runtime_report.py` |
| [ADR-007](ADR-007-runtime-manifest-and-verification.md) | Runtime manifest and verification | Accepted | `RUNTIME_OPS.md`, `observability/runtime_manifest.py` |
| [ADR-008](ADR-008-runtime-recovery-and-replay-semantics.md) | Runtime recovery and replay | Accepted | `RUNTIME_OPS.md`, `observability/runtime_recovery.py` |
| [ADR-009](ADR-009-runtime-schema-and-compatibility-semantics.md) | Runtime schema and compatibility | Accepted | `RUNTIME_OPS.md`, `observability/runtime_schema.py` |
| [ADR-010](ADR-010-bounded-runtime-audit-and-history.md) | Bounded runtime audit and history | Accepted | `RUNTIME_OPS.md`, `observability/runtime_history.py` |
| [ADR-011](ADR-011-runtime-baseline-and-drift-semantics.md) | Runtime baseline and drift | Accepted | `RUNTIME_OPS.md`, `observability/runtime_baseline.py` |
| [ADR-012](ADR-012-runtime-capability-and-deployment-profile-semantics.md) | Runtime capability profiles | Accepted | `RUNTIME_OPS.md`, `observability/runtime_capabilities.py` |
| [ADR-013](ADR-013-runtime-policy-and-guardrail-semantics.md) | Runtime policy and guardrails | Accepted | `RUNTIME_OPS.md`, `observability/runtime_policy.py` |
| [ADR-014](ADR-014-unified-runtime-index-and-consolidation.md) | Unified runtime index | Accepted | `RUNTIME_OPS.md`, `observability/runtime_index.py` |
| [ADR-015](ADR-015-runtime-stabilization-and-contract-freeze.md) | Stabilization and contract freeze | Accepted | `RUNTIME_CONTRACTS.md`, `RELEASE_CHECKLIST.md` |
| [ADR-016](ADR-016-repository-reproducibility-and-maintenance.md) | Repository reproducibility and maintenance | Accepted | `REPRODUCIBILITY.md`, `REPOSITORY_STANDARDS.md` |
| [ADR-017](ADR-017-v1-stable-release-and-operational-freeze.md) | v1.0.0 stable release and operational freeze | Accepted | `STABILITY_GUARANTEES.md`, `RELEASE_FINALIZATION.md` |
| [ADR-018](ADR-018-post-v1-maintenance-mode.md) | Post-v1 maintenance mode | Accepted | `MAINTENANCE_MODE.md`, `ISSUE_TRIAGE.md` |
| [ADR-019](ADR-019-post-v1-hardening-roadmap-planning-only.md) | Post-v1 hardening roadmap (planning-only) | Accepted (docs) | `post_v1_hardening.md`, `POST_V1_ADR_BACKLOG.md` |
| [ADR-020](ADR-020-release-governance-and-lifecycle.md) | Release governance and lifecycle | Accepted (docs) | `compatibility_policy.md`, `release_governance.md` |
| [ADR-021](ADR-021-operational-security-and-trust.md) | Operational security and trust | Accepted | `security/secrets_hygiene.md`, `v1_6_security_hardening_report.md` |
| [ADR-022](ADR-022-scalability-boundaries-and-controlled-evolution.md) | Scalability boundaries (v1.8) | Accepted (docs) | `scalability/operational_topologies.md`, `v1_8_scalability_boundaries_report.md` |
| [ADR-023](ADR-023-operational-intelligence-and-predictive-maintenance.md) | Operational intelligence (v1.9) | Accepted (advisory) | `operational_intelligence.md`, `v1_9_operational_intelligence_report.md` |
| [ADR-024](ADR-024-v2-transition-strategy.md) | v2 transition strategy (stewardship) | Accepted (planning) | `v2_transition_strategy.md`, `v2_transition_strategy_report.md` |
| [ADR-025](ADR-025-operational-semantics-verification.md) | Operational semantics (v2.x) | Accepted (verification) | `semantics/operational_invariants.md`, `v2x_operational_semantics_report.md` |
| [ADR-026](ADR-026-historical-traceability-and-ecosystem-continuity.md) | Historical traceability (v2.x) | Accepted (stewardship) | `stewardship/adr_lineage_map.md`, `v2x_historical_traceability_report.md` |
| [ADR-027](ADR-027-preservation-readiness-and-long-horizon-survivability.md) | Preservation readiness (v2.x) | Accepted (preservation) | `preservation/ecosystem_aging.md`, `v2x_preservation_readiness_report.md` |
| [ADR-028](ADR-028-legacy-stewardship-and-controlled-sunset.md) | Legacy stewardship (v2.x) | Accepted (legacy) | `legacy/legacy_state_definition.md`, `v2x_legacy_stewardship_report.md` |
| [ADR-029](ADR-029-live-telegram-operational-validation.md) | Live Telegram validation (v3.x) | Accepted (bounded) | `live_validation/`, `v3_live_telegram_validation_report.md` |
| [ADR-030](ADR-030-v3-2-operational-tooling-scope.md) | v3.2 operational tooling (read-only) | Accepted | `tools/ops_metrics_snapshot.py`, `v3_2_p1_exit_criteria.md` |
| [ADR-031](ADR-031-operational-analytics-layer.md) | v3.2 operational analytics (offline) | Accepted | `tools/ops_analytics_aggregate.py`, `v3_2_p2_exit_criteria.md` |

**Planning backlog (not accepted ADRs):** [POST_V1_ADR_BACKLOG.md](POST_V1_ADR_BACKLOG.md) · RFCs: [../rfc/README.md](../rfc/README.md)

## Stabilization docs (operators)

| Doc | Purpose |
|-----|---------|
| [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md) | Frozen artifact names, lifecycle, CLI, enums |
| [RUNTIME_MATURITY.md](RUNTIME_MATURITY.md) | Maturity scope and non-goals |
| [../OPERATOR_QUICKSTART.md](../OPERATOR_QUICKSTART.md) | 5-minute walkthrough |
| [../RUNTIME_LAYOUT_REFERENCE.md](../RUNTIME_LAYOUT_REFERENCE.md) | Per-artifact reference |
| [../RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md) | Release gates |
| [../DEPLOYMENT_QUICKSTART.md](../DEPLOYMENT_QUICKSTART.md) | Production-lite deploy walkthrough |
| [../RELEASE_PROCESS.md](../RELEASE_PROCESS.md) | Tagging and release discipline |
| [../DEMO_WALKTHROUGH.md](../DEMO_WALKTHROUGH.md) | Demo operational narrative |
