# WAL_PRESSURE

## Detection

- `wal_bytes` in drift monitor or scalability diagnostics > 256 MB
- Slow writes; long checkpoint times
- Backup/restore coupling with large `-wal` file

```bash
python3 tools/scalability_diagnostics.py --database-url "$DATABASE_URL"
```

## Mitigation

1. Quiesce writers (stop workers + app)
2. `PRAGMA wal_checkpoint(TRUNCATE)` on SQLite
3. Verify disk space
4. Resume workers

## Safe scaling guidance

- **Do not** add workers while WAL critical — readers increase WAL pressure
- Schedule checkpoint after bulk imports
- Stay T1/T2; Postgres migration is not an emergency WAL fix

## Rollback

- If checkpoint fails, restore from last known-good snapshot (T3 procedure)

## Evidence collection

- Record `wal_bytes` before/after
- Save drift monitor snapshot if enabled

## Escalation thresholds

| WAL size | Action |
|----------|--------|
| > 256 MB | Maintenance window checkpoint |
| > 500 MB | Stop workers; restore drill |
| Recurring weekly | ADR for DB evolution review (not automatic Postgres) |
