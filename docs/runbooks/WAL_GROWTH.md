# WAL_GROWTH

## Detection

- Drift monitor `wal_growth` finding
- Disk usage climbing on DB volume

## Mitigation

Quiesce → checkpoint → verify size drop.

## Safe restart

See [SQLITE_LONG_RUNNING_MAINTENANCE.md](SQLITE_LONG_RUNNING_MAINTENANCE.md).

## Validation

Compare WAL bytes before/after; drift report `OK`.

## Rollback

Restore DB backup if checkpoint fails.

## Evidence collection

- `wal_bytes` from drift baseline/current
- Filesystem `du` on DB directory

## Escalation thresholds

- WAL > 1GB → maintenance window within 24h
