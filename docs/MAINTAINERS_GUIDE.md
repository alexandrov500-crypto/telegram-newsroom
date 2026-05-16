# Maintainers guide — v3.2 operational tooling

For stewards of the **offline ops tooling** layer. Application/runtime maintenance: [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md).

## Quick validation

```bash
make stewardship-validate       # full ops program + normalization
make stewardship-audit-validate   # freeze integrity + audit bundle (post-freeze)
make immutable-baseline-validate   # archival fingerprint + immutable bundle
make archival-freeze-validate    # terminal archival seal (full chain)
make ci-test                    # runtime + smoke + contracts
make governance-validate        # governance contracts
```

## Regenerate reports (offline)

```bash
python3 tools/ops_metrics_snapshot.py --rotate          # capture (read-only)
python3 tools/ops_analytics_aggregate.py
python3 tools/ops_visualize.py
python3 tools/validate_ops_schema.py
python3 tools/generate_ops_html_report.py
python3 tools/generate_ops_index.py
python3 tools/build_ops_release_kit.py
```

Artifacts: `var/ops_history/`, `var/ops_reports/`, `var/ops_release_kit/` (gitignored).

## Verify archives

```bash
python3 tools/ops_archive.py --verify-only
python3 tools/validate_ops_schema.py
```

## Recovery drill

Follow [runbooks/offline_ops_recovery_drill.md](runbooks/offline_ops_recovery_drill.md). Sign [offline_recovery_certification.md](releases/offline_recovery_certification.md) on **180d** dormancy cadence (or after incident recovery).

## Post-freeze audits

```bash
python3 tools/check_freeze_integrity.py
python3 tools/build_stewardship_audit_bundle.py
make stewardship-audit-validate
```

Cadence (dormancy): [governance/dormancy_operations_policy.md](governance/dormancy_operations_policy.md) — historical calendar: [stewardship_operations_calendar.md](governance/stewardship_operations_calendar.md). Hotfixes: [runbooks/maintenance_hotfix_procedure.md](runbooks/maintenance_hotfix_procedure.md).

Deterministic CI check:

```bash
export OPS_FROZEN_UTC=2026-05-16T12:00:00Z
make stewardship-validate
```

## When NOT to change tooling

Do not add tools or features if the proposal involves:

- Live dashboards, WebSockets, or CDN assets
- Central metrics database or streaming pipeline
- Auto-remediation tied to analytics
- Imports from `publisher/` or worker mutation paths
- Background daemons

See [governance/long_term_stewardship.md](governance/long_term_stewardship.md) — “When NOT to build more tooling”.

## Governance dormancy (current mode)

Repository is **dormant** — preservation-only archival asset, not an actively maintained product. See [repository_preservation_notice.md](releases/repository_preservation_notice.md), [terminal_preservation_sealing_report.md](releases/terminal_preservation_sealing_report.md), and [dormancy_operations_policy.md](governance/dormancy_operations_policy.md).

- **90d:** `make archival-freeze-validate` (or documented subset) on canonical tag checkout
- **180d:** offline recovery drill
- **Incident only:** full chain + emergency preservation audit
- **No activity is healthy** between checks

## Governance restart (not implementation)

Repository is **frozen by default**. To propose a new lifecycle (not a hotfix):

1. Read [ADR-037](architecture/ADR-037-governance-restart-framework.md)
2. Complete [governance/restart_evaluation_template.md](governance/restart_evaluation_template.md)
3. Follow [runbooks/governance_restart_review.md](runbooks/governance_restart_review.md)

**ADR-037 does not authorize code.** No active restart is approved ([restart_readiness_declaration.md](releases/restart_readiness_declaration.md)).

## ADR escalation path (bounded hotfixes)

1. Draft ADR-038+ **only after** restart evaluation approves a new **program** (rare).
2. Run `make archival-freeze-validate` on tooling/governance doc PRs.
3. Operator sign-off per [operational_tooling_maintenance_policy.md](governance/operational_tooling_maintenance_policy.md).
4. Update freeze exception log in PR if applicable.

## Freeze policy summary

Tag **`v3.2-operational-tooling-freeze`** marks the immutable tooling baseline. Patches allowed; platform expansion rejected by default ([ADR-034](architecture/ADR-034-v3-2-finalization-and-stewardship.md)).

## Safe hotfix boundaries

| Allowed | Forbidden |
|---------|-----------|
| corrupt snapshot handling bug | publish/retry behavior change |
| SVG/MD formatting fix | new runtime hook |
| additive JSON field + doc | breaking schema without bump |
| test fixture updates | unbounded `var/` growth |

## Key documents

| Doc | Purpose |
|-----|---------|
| [v3_2_final_manifest.md](releases/v3_2_final_manifest.md) | Inventory |
| [v3_2_immutable_baseline.md](releases/v3_2_immutable_baseline.md) | Guarantees |
| [metrics_retention_policy.md](operations/metrics_retention_policy.md) | Retention |
| [v3_2_stewardship_handoff.md](releases/v3_2_stewardship_handoff.md) | Handoff |
