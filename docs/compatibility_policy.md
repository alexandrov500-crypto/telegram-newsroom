# Compatibility policy

Formal compatibility contract for the **telegram-newsroom** production-lite platform. Complements [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md) and [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md).

## Supported upgrade paths

| From | To | Path | Notes |
|------|-----|------|-------|
| v1.0.x | v1.0.y | **Patch** | Same runtime freeze; deps/docs/tests |
| v1.0.x | v1.1+ minor | **Minor** | Opt-in flags default off; additive app changes |
| Any | v2.0.0 | **Major** | ADR + contract test updates required |
| Git main | Operator deploy | **Operational** | Config/env only; tag optional |

Downgrade: supported for **patch** within same minor line if backup + inspection tree restored. Minor downgrade not guaranteed if opt-in flags were enabled.

## Compatibility levels

| Level | Meaning | Example |
|-------|---------|---------|
| **Frozen** | No breaking change without major version | 14 runtime JSON files, 11 CLIs |
| **Stable** | Backward compatible; defaults preserve prior behavior | `WORKER_RETRY_SAFE` default `false` |
| **Additive** | New optional JSON fields at `schema_version: 1` | Extra keys in `health_snapshot.json` |
| **Experimental** | Documented; may change in minor | Drift baseline semantics |
| **Unsupported** | Out of scope / rejected | New runtime artifact types |

## Allowed breaking surface

Breaking changes are permitted **only** on major version bump and require:

1. ADR accepted
2. Contract test updates
3. CHANGELOG + migration guide
4. Operator sign-off checklist ([release_governance.md](release_governance.md))

**Never breaking in 1.0.x / 1.x patch without major:**

- Runtime artifact filenames or lifecycle order
- Inspection CLI command registry
- Tri-state enums (`OK` / `WARNING` / `FAIL`)
- Snapshot directory layout (`OUTPUT_DIR/runtime/*.json`)
- Manifest checksum algorithm without dual-read period

## Freeze rules

- Runtime governance frozen at v1.0.0 (ADR-015, ADR-017).
- Maintenance-first mode ([MAINTENANCE_MODE.md](MAINTENANCE_MODE.md)).
- No new governance subsystems or mandatory observability stacks.

## Runtime contract rules

- **14** artifacts under `runtime/`; generation order `1..14`.
- `schema_version: 1` for inspection artifacts.
- SSOT: `observability/runtime_contracts.py` + `tests/contracts/test_runtime_contracts.py`.

## Evidence schema rules

- Required vs optional artifacts per `ARTIFACT_SPECS`.
- Additive fields only at schema v1 (ADR-009).
- Sidecars (`qualification.json`, `runtime_bundle.zip`) optional for WARNING, not FAIL of core 12.

## Snapshot compatibility rules

- `scripts/runtime_snapshot.sh` archives `OUTPUT_DIR/runtime/` (+ optional sidecars).
- `scripts/runtime_restore.sh` replaces inspection tree only — not a DB migration tool.
- Snapshot format: directory tree of frozen filenames; no zip schema version for inspection-only snapshots.

## Feature flag lifecycle rules

See [feature_flag_governance.md](feature_flag_governance.md). Summary: opt-in env flags default **off**; promotion to default-on requires minor release + ADR if behavior visible to operators.

## Operator expectations

- Read [v1_3_operational_envelope.md](v1_3_operational_envelope.md) before multi-worker deploy.
- Run `make release-check` before tagging.
- Run `python3 tools/release_readiness.py` before minor releases.
- Keep `backup_cli` + `runtime_snapshot` before risky changes ([migration_safety.md](migration_safety.md)).

## Backward compatibility matrix

| Surface | 1.0.0 | 1.1 opt-in | 1.3 opt-in | 2.0 (future) |
|---------|-------|------------|------------|--------------|
| Runtime JSON names | Frozen | Frozen | Frozen | ADR required |
| CLI commands | Frozen | Frozen | Frozen | ADR required |
| `WORKER_RETRY_SAFE` | N/A | Stable (off) | Stable | — |
| `PUBLISH_LOCK_STRICT` | N/A | Stable (off) | Stable | — |
| `RUNTIME_DRIFT_MONITOR` | N/A | — | Stable (off) | — |
| App pipeline behavior | Evolving | Evolving | Evolving | Major only |

## Related

- [deprecation_policy.md](deprecation_policy.md) · [release_governance.md](release_governance.md) · [evidence_lifecycle.md](evidence_lifecycle.md)
