# Restore procedure (production-lite)

Two layers: **database** (authoritative) and **inspection artifacts** (`OUTPUT_DIR/runtime/`). No new tooling — existing `backup_cli` and shell helpers.

## When to restore

- Bad upgrade, corrupted DB, or operator error
- Before rollback to prior git tag — restore data first

## A. Database + live runtime state (`backup_cli`)

### Create backup (routine)

```bash
python tools/backup_cli.py backup-create
python tools/backup_cli.py backup-list
python tools/backup_cli.py backup-validate var/backups/newsroom_backup_YYYYMMDD_HHMMSS.zip
```

### Restore

```bash
# Stop app.main first
python tools/backup_cli.py backup-restore var/backups/newsroom_backup_YYYYMMDD_HHMMSS.zip --with-runtime
```

- Restores SQLite DB and copies runtime files into `RUNTIME_STATE_DIR` when `--with-runtime` is set.
- See [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md) for details.

### Post-restore validation

```bash
make runtime-preflight RUNTIME_DIR=./var/runtime
# optional fresh nightly to refresh inspection tree:
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=./runtime_ops_output
scripts/runtime_sanity_check.sh
```

## B. Inspection artifact snapshot only

For ops JSON under `OUTPUT_DIR` (not `RUNTIME_STATE_DIR`):

### Snapshot (before change)

```bash
scripts/runtime_snapshot.sh
# → var/backups/runtime_snapshots/runtime_ops_YYYYMMDD_HHMMSS/
```

### Restore snapshot

```bash
scripts/runtime_restore.sh var/backups/runtime_snapshots/runtime_ops_YYYYMMDD_HHMMSS
make verify-runtime OUTPUT_DIR=./runtime_ops_output
```

This does **not** restore Telegram credentials, DB, or editorial memory in SQLite.

## Checksum verification workflow

```bash
export OUTPUT_DIR=./runtime_ops_output
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
# FAIL → read checksum_mismatches + Operator actions
make runtime-manifest OUTPUT_DIR="$OUTPUT_DIR"   # only if files are correct on disk
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

## Recognizing corrupted runtime state

| Signal | Meaning |
|--------|---------|
| `checksum_mismatches` | Manifest does not match files |
| Many `(missing)` in index | Incomplete nightly |
| `compatibility_status: FAIL` | schema_version or unreadable JSON |
| `recovery_status: FAIL` | Required runtime structure broken |
| Placeholder SHA in verify | Wrong directory (e.g. `runtime_samples`) |

## Related

- [FAILURE_DRILLS.md](FAILURE_DRILLS.md) · [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
