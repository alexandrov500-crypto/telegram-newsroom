# Phase 2 — Self-healing + operations

## Goals

- Survive failures without manual intervention
- Full audit trail (`correlation_id`, publish journal, pipeline ticks)
- Operationally boring: weeks without engineering touch

## What shipped (P2.0)

| Area | Implementation |
|------|----------------|
| Pipeline ticks | `pipeline_ticks` table, persist start/end per tick, stuck detection |
| Failed draft retry | `failed_drafts` table, exponential backoff, heartbeat batch |
| Correlation | `begin_pipeline_tick()` sets `correlation_id == tick_id`, stored in `draft_extras` |
| Publish journal | `correlation_id`, `publish_latency_ms`, `telegram_response` fields |
| Auto maintenance | `auto_maintenance.json` halts **publish only** (pipeline continues) |
| SQLite ops | `backup_sqlite_database`, `run_sqlite_integrity_check` (heartbeat) |
| Operator panel | `GET /ops/panel`, `GET /ops/panel.json`, `newsroom panel` |
| Deploy | `make deploy-safe` → `scripts/deploy-safe.sh` |

## Migration sequence

1. Deploy code (tables created via `Base.metadata.create_all` on worker start).
2. No manual SQL — SQLite migrations are additive (`create_all`).
3. Verify: `curl /ops/panel.json`, `make newsroom-status`.
4. Optional env tuning (see below).

## Risk analysis

| Risk | Mitigation |
|------|------------|
| Retry publishes duplicate | Idempotency keys `retry:{draft_id}:{n}` + publish journal |
| Stale `running` ticks | Heartbeat marks stale after `PIPELINE_TICK_STUCK_SEC` |
| Auto maintenance false positive | DEGRADED mode + publish-only halt; operator `maintenance off` |
| DB growth (ticks table) | Retention job (future); low row count per day |

## Rollback

1. `git checkout` previous tag on VPS.
2. Restore `var/runtime/backups/sqlite/newsroom_pre_deploy_*.db` over `data/newsroom.db`.
3. `docker compose up -d` + `curl /health`.

## Operator workflow

```bash
# Daily
make newsroom-status
make newsroom-panel          # or curl /ops/panel.json

# Incidents
make newsroom-diagnose
bash scripts/newsroom maintenance status
bash scripts/newsroom maintenance off --reason cleared

# Deploy (VPS)
make deploy-safe
```

## Environment knobs

```bash
PIPELINE_TICK_STUCK_SEC=1200      # mark running tick stale
PIPELINE_TICK_LONG_WARN_SEC=600
FAILED_DRAFT_MAX_RETRIES=5
SQLITE_BACKUP_KEEP=7
```

## Observability

- Logs: `grep correlation_id= tick-…` across `logs/*.log`
- HTTP: `/health`, `/ops/panel.json`, `/runtime/status`
- DB: `SELECT * FROM pipeline_ticks ORDER BY id DESC LIMIT 5`

## Post-deploy checklist

- [ ] `/health` → `healthy`, `conflict_detected: false`
- [ ] `/ops/panel.json` shows `last_tick.status` = `ok` after one interval
- [ ] No duplicate Telegram pollers (Mac control + VPS worker)
- [ ] `failed_drafts` empty or retrying (not growing unbounded)
- [ ] `PRAGMA integrity_check` OK in logs (`sqlite_integrity` alert absent)

## Remaining (P2.1+)

- OpenAI slow-request metrics dashboard
- Telegram FloodWait dedicated queue (partial: `publisher/retry.py`)
- Tick table retention cron
- SSH `newsroom restart` wrapper
