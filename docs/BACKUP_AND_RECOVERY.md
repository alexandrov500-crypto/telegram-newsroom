# Backup and recovery

## What to back up

| Asset | Why |
|-------|-----|
| SQLite `DATABASE_URL` file or Postgres volume | Canonical editorial + raw data |
| `RUNTIME_STATE_DIR` (`var/runtime` by default) | Topic memory, cadence, suppression, timeline, snapshots |
| Telethon session file or `TELETHON_SESSION_STRING` | Collector identity |
| `.env` (secret store) | Configuration (keep off-repo or encrypted) |

## SQLite snapshot (simple)

Stop writers (or accept brief lock) and copy the `.db` file plus `var/runtime/`.

## Restore

1. Restore DB file / Postgres dump into `DATABASE_URL`.
2. Restore `RUNTIME_STATE_DIR` tree (or start fresh — editorial memory rebuilds over time; cadence/suppression will reset behavior).
3. Verify Telethon session still valid.
4. `alembic upgrade head` if schema drifted between backup and restore target.
5. `python -m tools.admin_cli runtime-integrity-check`

## Rollback (application)

Prefer re-deploy previous git tag + matching migration revision (`alembic downgrade` one step only when migration authors document safe downgrade — many teams forward-fix data instead).

## DLQ recovery

Inspect `dlq-inspect`, fix upstream bug, then `dlq-replay` selectively. Do not bulk-replay without reading `reason` / `terminal` metadata.
