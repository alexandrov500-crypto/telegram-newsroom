# Changelog

All notable changes are documented here. Runtime governance is **frozen** as of **v1.0.0** ([STABILITY_GUARANTEES.md](docs/STABILITY_GUARANTEES.md)).

## Post-v1 maintenance expectations

**The project is maintenance-first, not expansion-first** ([MAINTENANCE_MODE.md](docs/MAINTENANCE_MODE.md)).

- **Compatibility-first** — preserve frozen runtime contracts, CLI registry, and Makefile targets in 1.0.x.
- **Operational freeze reaffirmed** — no new `runtime/*.json` governance artifacts without major version + ADR.
- **Changelog entries** — user-visible fixes, security dependency bumps, doc corrections; avoid listing internal refactors.
- **Pre-merge gate** — `make release-check` recommended for maintainers.
- **Issue/PR discipline** — see [ISSUE_TRIAGE.md](docs/ISSUE_TRIAGE.md) and [.github/pull_request_template.md](.github/pull_request_template.md).

## [Unreleased]

### Terminal preservation sealing (dormancy final pass)

- `terminal_preservation_sealing_report.md`; superseded banners on pre-dormancy stewardship cadence docs
- Publication manifest + preservation notice: governance commits, optional `v3.2-governance-dormant` tag
- Cadence/audit language aligned to 90d/180d; emergency preservation audit incident-only
- No code, CI, or new ADR

### ADR-038 governance dormancy protocol (preservation-only)

- ADR-038: dormant repository philosophy; preservation-over-activity
- Dormancy operations policy (90d/180d cadence), risk policy, suspension matrix
- repository_preservation_notice, final_dormancy_declaration, terminal_governance_closure
- dormancy_reactivation_trigger_guide; no code or validation pipelines

### ADR-037 governance restart framework (meta-only, no implementation)

- ADR-037: restart evaluation doctrine; preservation-first; anti-continuation safeguards
- Templates: restart evaluation, risk matrix, preservation priority policy
- Runbook: governance restart review; meta_governance_closure, restart_readiness_declaration
- **No active restart approved**; no code, branches, or validation chains added

### Archival closure and terminal repository state (v3.2)

- `v3_2_archival_closure_report.md`, `v3_2_publication_manifest.md`, `repository_terminal_state.md`
- `build_archival_integrity_seal.py`, `final_repository_preservation_audit.md`
- `v3_2_archival_freeze_tag.md`; `make archival-freeze-validate`
- Tag (after commit): `v3.2-archival-baseline`
- No new tooling layers or runtime changes

### Immutable stewardship certification (archival baseline)

- ADR-036: immutable certification philosophy and boundaries
- `build_repository_fingerprint.py`, `build_immutable_archive_bundle.py`
- `immutable_repository_certification.md`, `stewardship_preservation_declaration.md`
- `governance_preservation_audit.md`; `make immutable-baseline-validate`
- No runtime or tooling scope expansion

### Post-freeze stewardship operations (v3.2 baseline)

- Stewardship calendar, hotfix procedure, drift policy, branch policy
- `check_freeze_integrity.py`, `build_stewardship_audit_bundle.py`
- `stewardship_state_declaration.md`; `make stewardship-audit-validate`
- No runtime or scope expansion

### v3.2 git closure — immutable baseline publication

- Closure commit `ab7c92a`; tag `v3.2-operational-tooling-freeze` (points to closure commit)
- `v3_2_release_publication.md`, `v3_2_immutable_baseline.md`, `v3_2_freeze_validation.md`
- `MAINTAINERS_GUIDE.md`, `v3_2_transition_notice.md`, `v3_2_final_validation_summary.md`
- Post-tag record `556aedb` (freeze validation docs only)

### v3.2 FINAL — stewardship closure and repository normalization

- ADR-034: program closure, runtime/tooling separation, forbidden expansion paths
- `long_term_stewardship.md`, `offline_recovery_certification.md`, `operational_maturity_assessment.md`
- `v3_2_final_manifest.md`, `v3_2_stewardship_handoff.md`, `repository_normalization_report.md`
- `make stewardship-validate`; README/START_HERE/Makefile help normalization
- Tag (after commit): `v3.2-operational-tooling-freeze`
- No runtime or new tooling features

### v3.2 P4 operational packaging and tooling freeze

- ADR-033: release kit philosophy, portability, maintenance ownership
- `tools/build_ops_release_kit.py` → `var/ops_release_kit/<stamp>/` (VERSION, README, manifest, checksums)
- `tools/generate_ops_index.py` → static `var/ops_reports/index.html`
- `operational_tooling_maintenance_policy.md`, `offline_ops_recovery_drill.md`, `v3_2_tooling_freeze.md`
- `tests/integration/test_offline_ops_toolchain.py`; `make ops-release-validate`
- No runtime, service, or contract changes

### v3.2 P3 operational schema governance and export hardening

- ADR-032: schema lifecycle, deprecation, deterministic serialization
- `tools/validate_ops_schema.py` — snapshot/analytics/archive validation → `validation_report.json` / `.md`
- `tools/export_ops_bundle.py` — reproducible bundle with manifest + `checksums.sha256` under `var/ops_bundle/`
- `tools/generate_ops_html_report.py` — single-file static HTML with embedded SVG
- `utils/ops_schema_governance.py`, `utils/ops_bundle.py`; `OPS_FROZEN_UTC` for deterministic CI
- `operational_integrity_audit.md`, `v3_2_p3_exit_criteria.md`; `make ops-bundle-validate`
- No runtime pipeline, contract, or Telegram interaction changes

### v3.2 P2 operational analytics (offline)

- ADR-031: analytics layer on snapshot history
- `tools/ops_analytics_aggregate.py`, `ops_visualize.py`, `ops_archive.py`, `generate_shift_handoff.py`
- `utils/ops_analytics.py` — trends, anomalies, static SVG, archive gzip
- `metrics_retention_policy.md`; `make ops-analytics-validate`

### v3.2 P1 operational tooling (read-only)

- ADR-030: bounded ops tooling scope
- `tools/ops_metrics_snapshot.py`, `queue_introspection.py`, `publish_timeline_report.py`
- `utils/ops_tooling.py`, `utils/queue_introspection.py`
- Operator shift checklist; `make ops-tooling-validate`
- No publish/retry/scheduler/lock changes

### v3.2 stabilization and planning (docs-only)

- 72h operational findings template, production baselines, blameless postmortem template
- `v3_2_discovery.md`, `technical_debt_registry.md`
- Governance: production audit, stabilization freeze policy, v3.2 planning gate
- `make stabilization-validate` — no runtime changes

### v3.1 production-lite activation (controlled)

- `docs/operations/production_bootstrap.md` — P0–P3 startup phases
- `docs/operations/production_safeguards.md` — enforceable safeguards map
- `docs/operations/alerting_baseline.md`, `72h_stability_window.md`
- `docs/runbooks/controlled_activation.md`, `incident_response.md`
- `docs/releases/merge_summary_v3.1.md`, `release_integrity_checklist.md`, `deployment_checksum_notes.md`
- `make production-validate`; tag `v3.1-production-lite`
- Readiness grade **A**; merge-ready

### v3.1 production-lite rollout (staging sign-off package)

- `docs/staging/*` — environment checklist, live sign-off, operator sign-off, failure injection results
- `docs/operations/production_lite_rollout.md` — T0/T1/T2 phases with rollback triggers
- `docs/operations/observability_validation.md` — diagnostics v2 thresholds
- `docs/releases/v3.1-production-lite.md` — release notes
- `tools/staging_environment_verify.py` — read-only staging pre-flight (no Telegram API)
- `tests/staging/test_bounded_failure_injection.py` — CI-safe failure injection proxy
- Readiness grade **A−** until operator completes live staging (≤5 publishes)

### v3.x live Telegram validation (bounded tests + opt-in live)

- `docs/live_validation/*`, `docs/v3_live_telegram_validation_report.md`, ADR-029
- `tests/live/` session, floodwait, publish integrity, recovery
- `tools/live_telegram_diagnostics.py` (read-only)
- `make live-validation-validate`, `TELEGRAM_LIVE_VALIDATE=1` for live_telegram tests

### v2.x legacy stewardship (controlled sunset; docs + read-only guardrails)

- `docs/legacy/*` — legacy state, controlled sunset, recoverability, anti-patterns
- `docs/v2x_legacy_stewardship_report.md`, ADR-028
- `tools/legacy_guardrails.py`, `tests/legacy/`
- `make legacy-validate`, `make legacy-guardrails`

### v2.x preservation readiness (long-horizon survivability; docs + read-only guardrails)

- `docs/preservation/*` — ecosystem aging, dependency preservation, long-horizon recovery
- `docs/v2x_preservation_readiness_report.md`, ADR-027
- `tools/preservation_guardrails.py`, `tests/preservation/`
- `make preservation-validate`, `make preservation-guardrails`

### v2.x historical traceability (stewardship; docs + read-only guardrails)

- `docs/stewardship/*` — ADR lineage, release archaeology, operational history, ecosystem continuity
- `docs/v2x_historical_traceability_report.md`, ADR-026
- `tools/history_guardrails.py`, `tests/traceability/`
- `make traceability-validate`, `make history-guardrails`

### v2.x operational semantics (verification; docs + read-only guardrails)

- `docs/semantics/*` — invariants, forbidden states, recovery, consistency matrix, assumptions, governance
- `docs/v2x_operational_semantics_report.md`, ADR-025
- `tools/semantics_guardrails.py`, `tests/semantics/`
- `make semantics-validate`, `make semantics-guardrails`

### v2 transition strategy (stewardship; planning only)

- `docs/architecture/architectural_preservation.md`, `v2_transition_strategy.md`, `technical_debt_governance.md`
- `docs/architecture/complexity_budget.md`, `evolution_decision_matrix.md`, `future_scalability_realities.md`
- `docs/architecture/maintainer_longevity.md`, `operational_philosophy.md`
- `docs/v2_transition_strategy_report.md`, ADR-024
- `tools/architecture_guardrails.py`, `make architecture-validate`

### v1.9 operational intelligence (advisory; read-only)

- `utils/operational_trends.py`, `recovery_intelligence.py`, `operational_health.py`
- `tools/maintenance_forecast.py`, `drift_forecast.py`, `maintenance_recommendations.py`, `ops_summary.py`
- `docs/operational_intelligence.md`, `docs/v1_9_operational_intelligence_report.md`, ADR-023
- `tests/intelligence/`, `make intelligence-validate`, `make ops-summary`

### v1.8 scalability boundaries (documentation + read-only diagnostics)

- `docs/scalability/*` — topologies T0–T4, capacity, multi-worker, PostgreSQL evolution path (docs only), unsupported deployments, governance
- `docs/runbooks/scaling/*` (7 runbooks)
- `docs/v1_8_scalability_boundaries_report.md`, ADR-022
- `tools/scalability_diagnostics.py`, `tests/scalability/`
- `make scalability-test`, `make scalability-validate`

### v1.6 operational security & trust (opt-in)

- `docs/security/*`, `docs/runbooks/security/*`, ADR-021
- `utils/security_redaction.py` (`SECURITY_REDACTION=1`), `utils/artifact_integrity.py`
- `tools/dependency_audit.py`, `security_posture_check.py`, `security_readiness.py`
- `make security-validate`, `make security-readiness`

### v1.4 release governance (documentation + read-only gates)

- `docs/compatibility_policy.md`, `deprecation_policy.md`, `release_governance.md`
- `docs/migration_safety.md`, `evidence_lifecycle.md`, `feature_flag_governance.md`
- `docs/maintenance_matrix.md`, `docs/v1_4_release_governance_report.md`
- `docs/runbooks/upgrades/*`, ADR-020
- `tools/release_readiness.py`, `make governance-validate`, `make release-readiness`

### v1.3 resilience engineering (opt-in)

- `tests/soak/` harness and long-running stability tests
- `utils/runtime_drift_monitor.py`, `utils/scheduler_diagnostics.py`, `utils/resource_stability.py`
- `tools/evidence_retention.py`, `tools/soak_validate.py`
- Opt-in `RUNTIME_DRIFT_MONITOR`, `SCHEDULER_DIAGNOSTICS`
- Runbooks: WAL, evidence retention, long-running node, memory, Redis reconnect storm
- `docs/v1_3_operational_envelope.md`, `docs/v1_3_resilience_validation_report.md`
- `make soak-test`, `make resilience-validate`

### v1.1 chaos validation (opt-in reliability)

- `tests/chaos/` — deterministic chaos / recovery suite
- Opt-in `WORKER_RETRY_SAFE`, `PUBLISH_LOCK_STRICT` (default preserves v1.0.0 behavior)
- `utils/reliability_diagnostics.py`, `docs/runbooks/`, `docs/v1_1_operational_validation_report.md`
- `make chaos-test`, `tools/chaos_validate.py`, `.github/workflows/chaos-reliability.yml`

### Post-v1 hardening roadmap (planning-only)

- `docs/post_v1_hardening.md`, `POST_V1_TODO_BACKLOG.md`, `architecture/POST_V1_ADR_BACKLOG.md`
- `docs/rfc/RFC-001` … `RFC-010` drafts; ADR-019 (documentation scope)
- `tests/contracts/test_post_v1_hardening_docs.py`

### Production burn-in and operational evidence

- `docs/BURN_IN_REPORT.md`, `FAILURE_DRILLS.md`, `RESTORE_PROCEDURE.md`, `KNOWN_LIMITATIONS.md`
- `examples/failure_drills/` — sanitized broken inspection trees (frozen artifact names only)
- `scripts/runtime_snapshot.sh`, `runtime_restore.sh`, `runtime_sanity_check.sh`
- `tests/contracts/test_failure_drill_assets.py`, `test_shell_scripts.py`

### Maintenance mode (ADR-018)

- `docs/MAINTENANCE_MODE.md`, `ISSUE_TRIAGE.md`, `LTS_NOTES.md`, `DEPENDENCY_POLICY.md`
- GitHub issue and PR templates
- `tests/contracts/test_maintenance_docs.py`

## [1.0.0] - 2026-05-15

### Stable release

**Version identity:** `newsroom._version.VERSION = 1.0.0`, `RELEASE_STATUS = stable`.

### Finalized architecture

- Production-lite Telegram newsroom: collect → cluster (OpenAI) → moderate → publish.
- Single-node operational model; SQLite-first; optional Redis/Postgres documented.
- Bounded asyncio services — not a platform control plane.

### Operational philosophy

- **Deterministic artifacts** — stable JSON key order, frozen lifecycle, deterministic ZIP bundles.
- **Shell-first tooling** — Make + `python -m newsroom.cli`; no orchestration engine.
- **Inspection over enforcement** — policies describe assumptions; operators gate releases.
- **Stabilization over expansion** — compatibility-first maintenance ([MAINTENANCE_POLICY.md](docs/MAINTENANCE_POLICY.md)).

### Frozen governance statement

**Runtime governance and inspection model are operationally frozen as of v1.0.0.**

- 14 artifacts under `runtime/`, 11 inspection CLI commands, schema v1.
- Contract tests in `tests/contracts/` guard filenames, lifecycle, packaging, and docs.
- No new governance layers planned in 1.0.x without major revision.

### Packaging and OSS readiness

- MIT license, `MANIFEST.in` (docs, deploy, examples).
- `SECURITY.md`, `SUPPORT.md`, `docs/STABILITY_GUARANTEES.md`, `docs/RELEASE_FINALIZATION.md`.
- `make release-check` — contracts, smoke, quality, packaging consistency.

### Non-goals (reaffirmed)

- No Kubernetes, Helm, Terraform, Ansible, or in-repo deployment automation.
- No Prometheus/Grafana mandate, telemetry warehouse, policy engine, or web admin UI.
- No new `runtime/*.json` artifact types in 1.0.x without contract revision.

## [1.0.0-rc1] - 2026-05-15

### Architecture stabilization milestone

- Frozen runtime artifact lifecycle (14 JSON files), categories, and CLI inspection commands.
- ADR-015 stabilization and contract freeze.

### Governance freeze milestone

- Unified runtime index; inspection-only policy/capability/baseline/audit/recovery layers.

### Operational maturity milestone

- Production-lite deploy templates, operator quickstarts, demo samples.

### Repository reproducibility (ADR-016)

- `docs/REPRODUCIBILITY.md`, pinned `requirements-dev.txt`, `make quality`.

[1.0.0]: https://github.com/example/telegram-newsroom/releases/tag/v1.0.0
[1.0.0-rc1]: https://github.com/example/telegram-newsroom/releases/tag/v1.0.0-rc1
