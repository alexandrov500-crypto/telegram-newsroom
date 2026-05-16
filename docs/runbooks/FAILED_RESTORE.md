# FAILED_RESTORE

## Symptoms

- `backup_cli backup-restore` exits non-zero
- `runtime_restore.sh` incomplete tree
- `verify-runtime` FAIL after restore attempt

## Detection

- Corrupt zip, missing `database/newsroom.db` in archive
- Partial `OUTPUT_DIR/runtime/` (interrupted copy)
- Restore run while app still connected to SQLite

## Immediate Mitigation

1. **Stop** app and workers before any DB restore.
2. Do not delete sole backup zip — copy to staging path first.
3. For inspection-only issues, use fresh `OUTPUT_DIR` staging dir.

## Safe Recovery

**Database:**

```bash
# stop services first
python3 tools/backup_cli.py backup-restore /path/to/newsroom_backup_YYYYMMDD.zip --with-runtime
```

**Inspection tree:**

```bash
./scripts/runtime_restore.sh /path/to/snapshot_dir OUTPUT_DIR=./runtime_ops_staging
make verify-runtime OUTPUT_DIR=./runtime_ops_staging
```

## Validation Steps

```bash
make runtime-index OUTPUT_DIR=./runtime_ops_staging
make validate-recovery OUTPUT_DIR=./runtime_ops_staging
```

Compare checksums only on staging until OK; then swap paths deliberately.

## Rollback Strategy

Keep pre-restore copy of `newsroom.db` and `OUTPUT_DIR/runtime/` with timestamp suffix.

## Evidence Collection

- `metadata.json` inside backup zip
- `verify-runtime` / `runtime-index` CLI output
- [RESTORE_PROCEDURE.md](../RESTORE_PROCEDURE.md) checklist

## Escalation Notes

`runtime_snapshot.sh` does **not** replace DB restore — dual-layer model by design.
