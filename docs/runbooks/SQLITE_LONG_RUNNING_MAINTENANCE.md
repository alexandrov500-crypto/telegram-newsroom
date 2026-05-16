# SQLITE_LONG_RUNNING_MAINTENANCE

## Detection

- `newsroom.db-wal` growing without checkpoint
- `database is locked` under load
- Pipeline slowdown after weeks of uptime

## Mitigation

1. Stop app and workers (quiesce).
2. `sqlite3 newsroom.db "PRAGMA wal_checkpoint(TRUNCATE);"`
3. Optional `VACUUM` during maintenance window (see `SQLITE_VACUUM_INTERVAL_HOURS`).

## Safe restart

Single writer only. Restart one `app.main`, then workers if used.

## Validation

- `PRAGMA integrity_check;` → `ok`
- Smoke pipeline tick or `make runtime-nightly` on staging

## Rollback

Restore `backup_cli` zip from before maintenance.

## Evidence collection

- WAL / DB file sizes
- `utils/runtime_drift_monitor` report if `RUNTIME_DRIFT_MONITOR=1`

## Escalation thresholds

- WAL > 500MB with daily restarts → schedule maintenance
- Repeated corruption → restore backup; review multi-process writers
