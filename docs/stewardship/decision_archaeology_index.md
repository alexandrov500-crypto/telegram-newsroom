# Decision archaeology index

Cross-index: ADR ↔ RFC ↔ release phase ↔ docs. **Rejected** items stay visible.

## Accepted decision chains

| Phase | ADR | RFC (related) | Report / docs | Code (opt-in) |
|-------|-----|---------------|---------------|---------------|
| Governance | 001–014 | 001–004 (partial) | RUNTIME_OPS | observability/ |
| Freeze | 015–017 | — | STABILITY_GUARANTEES | — |
| Hardening plan | 019 | 005–010 backlog | post_v1_hardening | — |
| Chaos | — | RFC-010 | v1_1 report | WORKER_RETRY_SAFE, PUBLISH_LOCK_STRICT |
| Resilience | — | — | v1_3 reports | RUNTIME_DRIFT_MONITOR, SCHEDULER_DIAGNOSTICS |
| Governance | 020 | — | v1_4 report | release_readiness.py |
| Security | 021 | RFC-008 | v1_6 report | SECURITY_REDACTION |
| Scale | 022 | RFC-005,006 | v1_8 report | scalability_diagnostics.py |
| Intelligence | 023 | — | v1_9 report | maintenance_forecast, ops_summary |
| Stewardship | 024 | — | v2_transition_strategy_report | architecture_guardrails.py |
| Semantics | 025 | — | v2x_operational_semantics_report | semantics_guardrails.py |
| Traceability | 026 | — | v2x_historical_traceability_report | history_guardrails.py |
| Preservation | 027 | — | v2x_preservation_readiness_report | preservation_guardrails.py |
| Legacy | 028 | — | v2x_legacy_stewardship_report | legacy_guardrails.py |

## Rejected proposals (archaeology)

| Item | Type | Why not adopted |
|------|------|-----------------|
| RFC-005 PostgreSQL migration | RFC | Measured pain gate; docs-only path |
| RFC-006 distributed scheduling | RFC | T4 unsupported; single-node |
| RFC-006 K8s scheduling | RFC | Anti-platform-creep |
| Microservice split | Idea | ADR-024 non-goals |
| Mandatory Prometheus | Idea | ADR-003, FAQ |
| Autonomous self-heal | Idea | operational_philosophy |
| Enterprise compliance archive | Phase | Traceability/preservation explicit non-goal |
| Vendoring entire ecosystem | Phase | preservation phase non-goal |
| Full reproducible-build program | Phase | preservation phase non-goal |
| Shutdown automation | Phase | legacy phase non-goal |
| Archive-only repo conversion | Phase | legacy phase non-goal |
| Git history rewrite | Phase | Working rules forbidden |

## Frozen decisions

- 14 runtime artifacts, schema v1 (ADR-015)
- 11 inspection CLIs
- Default-off reliability flags preserving v1.0 paths
- No orchestration platform (ADR-003)

## Deferred complexity (“measured pain only”)

| Topic | Gate doc |
|-------|----------|
| PostgreSQL | postgresql_evolution_path.md |
| Multi-region | unsupported_deployments.md |
| New artifact type | v2_transition_strategy.md |
| Default-on flag | feature_flag_governance.md |

## Non-adopted technologies (explicit)

Kubernetes (as required platform), Kafka/NATS, service mesh, ML ops platform, external telemetry warehouse, contributor bureaucracy tooling.

## Link maintenance

Run `make traceability-validate` after adding ADR, RFC, or phase report.
