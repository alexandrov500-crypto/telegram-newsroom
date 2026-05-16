# SQLITE_LOCKED

## Symptoms

- `database is locked` / `SQLITE_BUSY` in app or worker logs
- Pipeline ticks hang; drafts stuck in `publishing`
- Slow admin bot responses

## Detection

- Concurrent processes: `app.main` + multiple `workers.*` on same `DATABASE_URL` file
- Second writer: Telethon `SQLiteSession` on same disk as newsroom DB
- WAL files growing: `newsroom.db-wal`

## Immediate Mitigation

1. Ensure **single writer** policy ([KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)).
2. Stop surplus worker processes; keep one scheduler owner.
3. Avoid `backup_cli restore` while app is running.

## Safe Recovery

1. Quiesce: stop app and all workers.
2. Optional: `sqlite3 newsroom.db "PRAGMA wal_checkpoint(TRUNCATE);"`
3. Start single app instance; then workers if needed (Redis queue mode).

## Validation Steps

```bash
python3 tools/backup_cli.py backup-create   # after stable
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=./runtime_ops_output
```

## Rollback Strategy

Restore from last good `backup_cli` zip taken **before** lock storm (stop writers first).

## Evidence Collection

- Process list showing multiple Python newsroom processes
- DB path from `DATABASE_URL`
- `SQLITE_LOCKED` log excerpts with timestamps

## Escalation Notes

For sustained write load, plan PostgreSQL opt-in path (RFC-005) — not a v1.0.x contract change.
