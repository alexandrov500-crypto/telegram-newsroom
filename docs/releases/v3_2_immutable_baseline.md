# v3.2 immutable baseline

Immutable guarantees at tag **`v3.2-operational-tooling-freeze`**. This document is normative for stewardship; runtime remains governed separately (ADR-015, v1.0.0 freeze).

## Runtime guarantees (unchanged by v3.2 tooling)

| Area | Guarantee |
|------|-----------|
| Publish semantics | Unchanged — no tooling PR modifies publish path |
| Retry semantics | Unchanged |
| Scheduler | Unchanged |
| Locks | Unchanged |
| Runtime contracts | Frozen `runtime/*.json` schema v1 — 14 artifacts |

Tooling may **read** counter-shaped diagnostics; it must not **drive** retries, publishes, or schedules.

## Tooling guarantees (frozen at v3.2)

| Guarantee | Mechanism |
|-----------|-----------|
| Offline only | No network in validate/export/kit paths |
| Deterministic | `frozen_utc_now()` / `OPS_FROZEN_UTC`; sorted JSON manifests |
| Bounded storage | 200 files / 20MB history; 30MB kit cap |
| Reproducible exports | `export_ops_bundle.py`, `build_ops_release_kit.py` |
| No runtime coupling | Contract tests; no publisher imports in ops tools |
| Corruption isolation | Skip corrupt JSON; report in validation |
| Portable artifacts | Single-file HTML; checksum manifests |

## Governance guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| ADR-governed changes only | ADR-030–034; new work → ADR-035+ cycle |
| Freeze discipline | [v3_2_tooling_freeze.md](v3_2_tooling_freeze.md) |
| Operational audits | [operational_integrity_audit.md](../operations/operational_integrity_audit.md) |
| Maintenance policy | [operational_tooling_maintenance_policy.md](../governance/operational_tooling_maintenance_policy.md) |
| CI enforcement | `make stewardship-validate` |

## What may change after the tag

- Documentation clarifications
- Bugfixes preserving schemas and determinism
- Additive schema fields with ADR note
- Security dependency pins (tooling-adjacent only)

## What must not change without new ADR program

- Runtime semantics or frozen contracts
- Tooling → runtime feedback loops
- New daemons, databases, or hosted dashboards
- Breaking snapshot/analytics schema without version bump

## Verification

```bash
make stewardship-validate
git describe --tags --match 'v3.2-operational-tooling-freeze'
```
