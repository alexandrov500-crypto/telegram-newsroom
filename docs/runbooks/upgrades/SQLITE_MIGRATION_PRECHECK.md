# SQLITE_MIGRATION_PRECHECK

## Prerequisites

- Alembic revision identified (app layer)
- Maintenance window scheduled

## Backup requirements

- `backup_cli backup-create` mandatory
- Copy raw `newsroom.db` + `-wal` + `-shm` if present

## Validation steps

1. `sqlite3 newsroom.db "PRAGMA integrity_check;"`
2. Record file sizes (DB + WAL)
3. Stop **all** writers (app, workers, Telethon on same file if shared — avoid)
4. Run migration
5. Re-run integrity check
6. App smoke: one pipeline tick

## Rollback steps

- Stop writers
- Restore backup zip via `backup_cli backup-restore`
- Never partial-restore WAL without DB

## Evidence verification

- Pipeline metrics move; inspection nightly still runs

## Degraded-mode checks

- If migration fails mid-way, do not start writers until restore complete
