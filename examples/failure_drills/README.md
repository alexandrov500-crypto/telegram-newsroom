# Failure drills (v1.0.0)

Sanitized **broken** inspection trees for operator training. Uses only the **14 frozen** `runtime/*.json` names — no new artifact types.

```bash
export DRILL=examples/failure_drills/broken_checksum
python3 -m newsroom.cli verify-runtime --path "$DRILL" --strict
```

See [docs/FAILURE_DRILLS.md](../../docs/FAILURE_DRILLS.md).

| Directory | Teaches |
|-----------|---------|
| `broken_checksum/` | Manifest checksum mismatch |
| `missing_required/` | Incomplete nightly output |
| `invalid_schema/` | Unsupported schema_version |
| `warning_optional_missing/` | Optional baseline/drift absent |
| `missing_bundle/` | Missing `runtime_bundle.zip` sidecar |
