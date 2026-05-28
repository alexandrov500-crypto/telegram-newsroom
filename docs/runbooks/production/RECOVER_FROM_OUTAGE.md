# Recover from outage

## Symptoms

- `/health` → `unhealthy` or unreachable
- No new drafts for >2× pipeline interval
- Telegram bot not responding

## Diagnosis

```bash
make newsroom-status
make newsroom-diagnose
curl -s http://127.0.0.1:8080/ops/panel.json | python3 -m json.tool
tail -80 logs/local-run.log
```

Check `conflict_detected`, `operational_mode`, `auto_maintenance.active`.

## Commands

```bash
# Mac control — ensure VPS stopped if running locally
docker stop telegram-newsroom   # on VPS if Mac is worker

bash scripts/stop_local_newsroom.sh
make mac-start

# Or VPS worker
cd deploy/timeweb && docker compose up -d newsroom
```

## Expected

- `/health` → `"status":"healthy"` or `"degraded"` (not unhealthy)
- `pipeline.last_tick.status` → `ok` within one interval

## Rollback

Restore SQLite backup: `var/runtime/backups/sqlite/newsroom_pre_deploy_*.db`  
Redeploy previous image tag.
