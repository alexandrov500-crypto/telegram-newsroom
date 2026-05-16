# Artifact integrity

Trust model for inspection evidence without changing frozen `runtime_manifest.json` format.

## Authoritative verification

- `python -m newsroom.cli verify-runtime` — manifest checksums (frozen contract)
- `runtime_manifest.json` remains SSOT for nightly tree

## Supplemental integrity (opt-in)

- `utils/artifact_integrity.py` — SHA-256 catalog of `OUTPUT_DIR/runtime/*.json`
- Written to operator path (e.g. `var/security/integrity_report.json`) — **not** a 15th runtime artifact
- Used for tamper detection between snapshot and restore

## Snapshots

- `runtime_snapshot.sh` — directory copy; verify after restore with `verify-runtime`
- Tamper: unexpected checksum_mismatches → [EVIDENCE_TAMPERING.md](../runbooks/security/EVIDENCE_TAMPERING.md)

## Evidence archives

- `backup_cli` zip — confidential; integrity via file hash offline
- `evidence_retention.py verify-manifest` — delegates to verify-runtime

## Drift baselines

- Operator JSON; not frozen — protect file permissions

## Release artifacts

- Git tag + `make release-check` log
- No in-repo binary signing (operator responsibility)

## Tamper detection workflow

1. Capture supplemental report before change
2. Apply change
3. `verify_integrity_report` or re-run `verify-runtime`

## Related

- [evidence_lifecycle.md](../evidence_lifecycle.md)
