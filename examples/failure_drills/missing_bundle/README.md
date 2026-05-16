# Drill: missing runtime_bundle.zip

**Cause:** Complete `runtime/` tree; no `runtime_bundle.zip` at output root (sidecar).

**Run:**

```bash
python3 -m newsroom.cli validate-recovery --path .
```

**Expected:**

- `recovery_status: WARNING`
- `bundle_extractable: False`
- `recovery_warnings: missing_optional:runtime_bundle.zip`

**Recovery:** Re-run nightly bundle step or restore from snapshot/backup.
