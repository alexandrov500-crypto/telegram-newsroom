# ADR-032: Operational schema governance (v3.2 P3)

**Status:** Accepted  
**Date:** 2026-05-16  
**Depends on:** ADR-030 (P1 tooling), ADR-031 (P2 analytics)

## Decision

Introduce **bounded schema governance** for the offline operational tooling stack:

- Versioned snapshot wrapper, embedded diagnostics, and analytics exports
- Static validation (`tools/validate_ops_schema.py`)
- Reproducible export bundles (`tools/export_ops_bundle.py`)
- Portable static HTML report (`tools/generate_ops_html_report.py`)

No changes to production-lite runtime, publish pipeline, contracts, or live Telegram behavior.

## Schema lifecycle

| Layer | Current version | Owner | Storage |
|-------|-----------------|-------|---------|
| Metrics snapshot wrapper | `1` | P1 `utils/ops_tooling.py` | `var/ops_history/*.json` |
| Embedded diagnostics | `2` | `tools/live_telegram_diagnostics.py` | Inside snapshot `diagnostics` |
| Analytics export | `1` | P2 `utils/ops_analytics.py` | `var/ops_reports/`, bundles |
| Validation report | `1` | P3 `utils/ops_schema_governance.py` | `validation_report.json` |
| Bundle manifest | `1` | P3 `utils/ops_bundle.py` | `var/ops_bundle/*/manifest.json` |

### Diagnostics schema lifecycle

1. **Introduce:** bump `diagnostics.schema_version`; keep snapshot wrapper at `1` until wrapper fields change.
2. **Validate:** P3 validator WARNs when embedded version present and mismatched; absent version allowed for legacy snapshots.
3. **Deprecate:** document in CHANGELOG; retain read support for N=2 minor cycles.
4. **Remove:** only after archive rotation and operator sign-off; never auto-delete runtime data.

### Snapshot schema versioning

- Wrapper `schema_version` increments only when top-level snapshot fields change.
- Filename convention remains UTC-sortable: `ops_metrics_YYYYMMDDTHHMMSSZ.json`.
- Rotation bounds unchanged (200 files / 20MB).

### Analytics schema compatibility

- Consumers must tolerate unknown keys (forward compatible).
- Required export keys listed in `REQUIRED_ANALYTICS_EXPORT_FIELDS` (P3).
- Breaking removal of `trends` keys requires analytics `schema_version` bump.

## Deprecation policy

| Action | Rule |
|--------|------|
| Field removal | Forbidden without major version bump |
| Field rename | Add alias for one release; then deprecate |
| Semantic change | New `interpretation` string; document in ADR |
| Tool removal | Exit criteria + Makefile target removal in next minor |

## Backward compatibility guarantees

- P3 tools read P1 snapshots without migration scripts.
- Corrupt JSON skipped; never abort entire batch.
- Archives verified by gzip JSON parse, not runtime replay.
- Production runtime artifacts (`runtime/*.json`) remain frozen and out of scope.

## Corruption handling strategy

1. **Detect:** JSON parse failure → `CORRUPT` in validation report.
2. **Isolate:** file excluded from analytics series; listed in `skipped_corrupt`.
3. **Report:** validation + bundle manifest still generated from healthy files.
4. **Recover:** restore from `var/ops_archive/` or re-run `ops_metrics_snapshot.py`.
5. **Never:** auto-delete corrupt files; operator decides.

## Schema evolution rules

1. Prefer additive fields.
2. Bump version integer on incompatible change.
3. Document every bump in CHANGELOG and exit criteria.
4. CI contract tests assert version constants and forbidden patterns.

## Forbidden breaking changes

- Removing `read_only`, `no_telegram_api_calls`, `no_redis_mutations` from snapshots
- Changing counter semantics without new `interpretation` key
- Requiring network or Redis for validation/export
- Coupling bundle export to live worker state
- Writing into `runtime/` or mutating frozen contracts

## Migration philosophy

**No online migrations.** Operators:

1. Run `validate_ops_schema.py` after upgrades.
2. Export bundle before/after for diff.
3. Archive old snapshots if needed (`ops_archive.py`).
4. Roll back tools only (delete `var/ops_reports/`, `var/ops_bundle/`).

## Deterministic serialization requirements

- JSON: `sort_keys=True`, `indent=2`, trailing newline
- Manifest file list sorted by `path`
- Checksums: SHA-256 hex, stable path separators (`/`)
- Timestamps: `OPS_FROZEN_UTC` for CI; otherwise UTC `generated_at` only
- SVG/HTML: stable key order; no external assets

## Allowed (P3)

| Capability | Mechanism |
|------------|-----------|
| Schema validation | `tools/validate_ops_schema.py` |
| Reproducible bundle | `tools/export_ops_bundle.py` |
| Static HTML report | `tools/generate_ops_html_report.py` |
| Integrity audit doc | `docs/operations/operational_integrity_audit.md` |

## Forbidden (P3)

- Live dashboards, CDNs, JS frameworks
- Persistent databases, async workers, background services
- External telemetry vendors
- Runtime pipeline / contract changes

## CI

- `make ops-bundle-validate`
- Fixture-only reproducibility tests with `OPS_FROZEN_UTC`

## References

- [operational_integrity_audit.md](../operations/operational_integrity_audit.md)
- [v3_2_p3_exit_criteria.md](../releases/v3_2_p3_exit_criteria.md)
- [metrics_retention_policy.md](../operations/metrics_retention_policy.md)
