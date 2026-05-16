# Evidence lifecycle

How inspection evidence is created, retained, versioned, and archived without contract chaos.

## Evidence types

| Type | Location | Mutable by inspection CLIs? |
|------|----------|------------------------------|
| Runtime JSON (12 required + 2 optional) | `OUTPUT_DIR/runtime/` | No (read-only validation) |
| Sidecars | `OUTPUT_DIR/*.json`, `runtime_bundle.zip` | No |
| DB + runtime state | `DATABASE_URL`, `RUNTIME_STATE_DIR` | App pipeline only |
| Drift baselines | Operator-captured JSON (opt-in) | External to freeze |
| CI artifacts | `ci-artifacts/` | Retention tooling |

## Evidence retention lifecycle

1. **Generate** — `make runtime-nightly`
2. **Validate** — inspection CLIs
3. **Snapshot** — `runtime_snapshot.sh`
4. **Archive** — operator copy / CI upload
5. **Prune** — `tools/evidence_retention.py`, `tools/runtime_retention.py`
6. **Dispose** — operator policy; not automated in-app

## Evidence versioning

- Inspection artifacts: `schema_version: 1` only (frozen).
- Tool reports (`drift_report`, `soak_harness_report`): `schema_version: 1` in tool output; not part of 14-artifact freeze.
- `CHANGELOG` is human version SSOT for releases.

## Manifest evolution rules

- `runtime_manifest.json` checksums list **present** files only.
- Algorithm changes require major version or dual-validation period (documented in ADR).
- `verify-runtime` is authoritative for checksum failures.

## Archive compatibility

- Zip backups (`backup_cli`) include DB + runtime state files — not a substitute for full `OUTPUT_DIR` unless operator copies separately.
- Snapshot dirs portable across patch versions if frozen filenames unchanged.

## Drift baseline lifecycle

- Capture: `RUNTIME_DRIFT_MONITOR=1` or manual `capture_baseline()`
- Compare: weekly on long-running nodes
- Retire: delete baseline file when rebuilding node; recapture after intentional config change

## Inspection schema stability

- Additive fields only in 1.x (ADR-009).
- New required fields → major version + contract tests.
- `check-compatibility` validates supported schema set.

## Future evolution without contract chaos

1. Propose ADR
2. Update `runtime_contracts.py` + contract tests (major only for breaks)
3. Update [compatibility_policy.md](compatibility_policy.md) matrix
4. Ship migration runbook

## Related

- [compatibility_policy.md](compatibility_policy.md) · [runbooks/EVIDENCE_RETENTION.md](runbooks/EVIDENCE_RETENTION.md)
