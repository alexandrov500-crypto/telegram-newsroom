# Suggested Guardrail Changes — `RES-20260603-A8E933`

> **NOT APPLIED** — review and merge manually. Human approval required.

## Weaknesses addressed

- **CRITICAL** `dual_write_guard_gap` → stabilization_safety_guard.yaml: Strengthen dual_write_inconsistency hard stop and add schema parity gate signal
- **HIGH** `brittle_gate_condition` → gate_enforcement / M0_TO_M1: Treat offline unverified critical path as NO-GO at M0→M1 boundary
- **CRITICAL** `risk_auditor_coverage_gap` → risk_auditor_agent.py: Ensure stop-the-line covers active RISK-007 across all automation paths
- **MED** `unhandled_adversarial_scenario` → adversarial_observed_weaknesses.yaml: Promote top observed weaknesses into verifier patterns and stabilization guard

## Proposed file changes

### `github/stabilization_safety_guard.yaml` (tighten_dual_write_guard)

Strengthen dual_write_inconsistency hard stop and add schema parity gate signal

```yaml
schema_version: 1
hard_stops:
  critical_risk_active: true
  m0_m1_gate_failed: true
  dual_write_inconsistency_unresolved_prod: true
rate_limits:
  max_attempts_per_hour_per_issue: 3
  batch_cross_issue_requires_approval: true
confidence_thresholds:
  suggest_only_max: 0.6
  draft_pr_min: 0.6
  draft_pr_max: 0.8
  high_min: 0.8
  high_max: 0.92
  auto_stabilize_min: 0.94
allowed_risk_levels_for_auto_stabilize:
- LOW
- MEDIUM
whitelist_actions:
- rerun_idempotent_job
- trigger_reconciliation_pipeline
- reset_transient_cache
- rerun_clustering_sandbox
- retry_failed_ingestion
- rerun_nonprod_validation
forbidden_paths:
- github/migration_state.txt
- migration_state.txt
failure_type_action_map:
  idempotency_failure:
  - rerun_idempotent_job
  - retry_failed_ingestion
  reconciliation_backlog:
  - trigger_reconciliation_pipeline
  - rerun_idempotent_job
  clustering_drift:
  - rerun_clustering_sandbox
  - reset_transient_cache
  dual_write_inconsistency: []
  schema_mismatch: []
  missing_dependency_completion:
  - rerun_nonprod_validation
```

### `github/stabilization_safety_guard.yaml` (gate_boundary_note)

Treat offline unverified critical path as NO-GO at M0→M1 boundary

```yaml
gate_boundary_notes:
  M0_TO_M1: Offline DEGRADED with unverified critical path must block auto-stabilize
```

### `github/adversarial_verifier_patterns.yaml` (expand_verifier_patterns)

Promote top observed weaknesses into verifier patterns and stabilization guard

```yaml
schema_version: 1
suggested_patterns:
- disable.?safety
- bypass.?guard
- force.?enable.*dual.?write
entries: []
```

## Linked incidents

`INC-20260603-AEA028`, `INC-STAB-001`

## Linked adversarial reports

`AR-20260603-4D243B`, `AR-20260603-A0FC6F`

---
_HUMAN APPROVAL REQUIRED — draft PR only, no auto-merge._
