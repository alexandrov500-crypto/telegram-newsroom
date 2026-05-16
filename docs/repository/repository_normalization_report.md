# Repository normalization report (v3.2 FINAL)

Verification pass for documentation links, Makefile targets, and `var/` expectations. Generated as part of v3.2 FINAL closure.

**Verification date:** 2026-05-16  
**Gate:** `make stewardship-validate` + `tests/contracts/test_repository_normalization.py`

## Verified paths (documentation)

| Path | Status |
|------|--------|
| `docs/START_HERE.md` | ☑ v3.2 P1–P4 + FINAL links |
| `docs/architecture/README.md` | ☑ ADR-030–034 index |
| `docs/architecture/ADR-030` … `ADR-034` | ☑ present |
| `docs/governance/long_term_stewardship.md` | ☑ |
| `docs/governance/operational_tooling_maintenance_policy.md` | ☑ |
| `docs/releases/v3_2_final_manifest.md` | ☑ |
| `docs/releases/v3_2_stewardship_handoff.md` | ☑ |
| `docs/runbooks/offline_ops_recovery_drill.md` | ☑ |
| `docs/operations/metrics_retention_policy.md` | ☑ |
| `docs/operations/operational_integrity_audit.md` | ☑ |

## Stale reference check

| Check | Result |
|-------|--------|
| Makefile lists `ops-tooling-validate` … `stewardship-validate` | ☑ |
| No broken `make ops-*` target names in contract tests | ☑ |
| P3/P4 tools referenced in START_HERE | ☑ |
| `v3.2-ops-tooling-frozen` vs `v3.2-operational-tooling-freeze` | Normalized to **latter** in handoff |

## Tooling directory map

```
tools/
  ops_metrics_snapshot.py      # P1 capture
  queue_introspection.py       # P1 read-only queue
  publish_timeline_report.py   # P1 timeline
  ops_analytics_aggregate.py   # P2 analytics
  ops_visualize.py             # P2 SVG
  ops_archive.py               # P2 archive
  generate_shift_handoff.py    # P2 handoff
  validate_ops_schema.py       # P3 validation
  export_ops_bundle.py         # P3 bundle
  generate_ops_html_report.py  # P3 HTML
  build_ops_release_kit.py     # P4 release kit
  generate_ops_index.py        # P4 index
  live_telegram_diagnostics.py # diagnostics embed (read-only)

utils/
  ops_tooling.py
  ops_analytics.py
  ops_schema_governance.py
  ops_bundle.py
  ops_release_kit.py
  ops_index.py
  queue_introspection.py

tests/
  tools/                       # unit tests + fixtures/ops_history
  contracts/                   # doc + schema contracts
  integration/                 # offline e2e toolchain
```

## `var/` retention expectations

| Directory | Purpose | Gitignored | Bounds |
|-----------|---------|------------|--------|
| `var/ops_history/` | Active snapshots | Yes | 200 files / 20MB |
| `var/ops_reports/` | Regenerated reports + index | Yes | Operator-managed |
| `var/ops_archive/` | Gzip archives | Yes | 50MB/run default |
| `var/ops_bundle/` | Export bundles | Yes | 30MB cap |
| `var/ops_release_kit/` | Release kits | Yes | 30MB cap |

Runtime artifacts remain under `var/runtime/` (separate governance, ADR-015).

## Archive expectations

- Format: `var/ops_archive/YYYY-MM/ops_metrics_*.json.gz`
- Verify: `python3 tools/ops_archive.py --verify-only`
- Recovery: gunzip → `var/ops_history/` or re-snapshot

## README / Makefile normalization (FINAL)

| Item | Action |
|------|--------|
| README | Added v3.2 offline ops tooling section |
| `make help` | Lists ops validation + stewardship targets |
| `.gitignore` | All five `var/ops_*` paths ignored |

## Contract enforcement

Automated checks: `tests/contracts/test_repository_normalization.py`
