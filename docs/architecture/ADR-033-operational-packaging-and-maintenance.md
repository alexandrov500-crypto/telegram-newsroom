# ADR-033: Operational packaging and maintenance (v3.2 P4)

**Status:** Accepted  
**Date:** 2026-05-16  
**Depends on:** ADR-030–032 (P1–P3 operational tooling)

## Decision

Close the v3.2 tooling cycle with **offline release packaging** and **maintenance governance**:

- `tools/build_ops_release_kit.py` → `var/ops_release_kit/<stamp>/`
- `tools/generate_ops_index.py` → `var/ops_reports/index.html`
- Maintenance policy and recovery drill documentation
- `make ops-release-validate` as final gate

No runtime semantics, publish pipeline, or live observability hooks.

## Tooling packaging philosophy

1. **Self-contained:** each release kit includes HTML, analytics, validation, manifest, checksums, VERSION, README.
2. **Reproducible:** same snapshots + `OPS_FROZEN_UTC` → identical manifest file list and hashes.
3. **Portable:** copy directory or tarball; open HTML offline.
4. **Auditable:** SHA-256 manifest; schema versions in index and validation report.
5. **Bounded:** kit size cap aligned with P3 bundle limit (30MB default).

## Portability guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| No install step | Plain files under `var/` |
| No network at view time | Static HTML/SVG only |
| Cross-platform | UTF-8 JSON/text; forward slashes in manifest |
| Recoverability | Drill doc + regenerate from snapshots |

## Offline-first requirements

- All generators run with repository Python + stdlib + existing utils only
- No Redis, Telegram, or worker process required
- Missing history → empty analytics with graceful README notes
- Corrupt files isolated per ADR-032

## Deterministic artifact expectations

- JSON: `sort_keys=True`, trailing newline
- Manifest paths lexicographically sorted
- Kit stamp from `frozen_utc_now()` (or `OPS_FROZEN_UTC` in CI)
- CI integration test proves end-to-end hash stability

## Maintenance ownership model

| Area | Owner | Cadence |
|------|-------|---------|
| Schema bumps | Engineering + operator review | Per ADR-032 |
| Release kit format | Engineering | v3.2.x patches only |
| Snapshot capture | Operator cron | 4h recommended |
| Archive rotation | Operator | Weekly |
| Reproducibility gate | CI | Every PR touching `tools/` or `utils/ops_*` |

See [operational_tooling_maintenance_policy.md](../governance/operational_tooling_maintenance_policy.md).

## Release compatibility guarantees

- Kits remain readable for N=2 minor tooling versions (forward-compatible JSON keys)
- `OPS_TOOLING_RELEASE_VERSION` in `VERSION` file
- Runtime `runtime/*.json` contracts remain **out of scope** and frozen

## Allowed

| Capability | Tool |
|------------|------|
| Static packaging | `build_ops_release_kit.py` |
| Deterministic bundles | P3 `export_ops_bundle` (embedded in kit build) |
| Portable exports | Release kit directory |
| Offline release kits | `var/ops_release_kit/` |
| Maintenance automation (offline) | Makefile targets, pytest |
| Static index | `generate_ops_index.py` |

## Forbidden

| Anti-pattern | Reason |
|--------------|--------|
| Hosted dashboards | Scope creep; network dependency |
| Telemetry ingestion services | Runtime coupling |
| Persistent analytics servers | Violates bounded storage |
| Runtime integrations / hooks | Zero-impact rule |
| Live synchronization | No daemons |
| Cloud/CDN assets in reports | Offline portability |
| Interactive UI / web apps | Out of scope |

## CI

- `make ops-release-validate` (aggregates P1–P3 + P4 integration)

## References

- [operational_tooling_maintenance_policy.md](../governance/operational_tooling_maintenance_policy.md)
- [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md)
- [v3_2_tooling_freeze.md](../releases/v3_2_tooling_freeze.md)
