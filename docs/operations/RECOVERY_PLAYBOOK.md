# Recovery playbook

## Cold restart (VPS reboot)

```bash
cd /path/to/newsroom
docker compose -f deploy/docker-compose.prod.yml up -d
# Stale ticks finalize on startup (committed_reject stale_tick_timeout)
curl -s http://127.0.0.1:8080/health/runtime
```

## Stale pipeline ticks

Automatic on startup + watchdog. Manual:

```bash
python3 -c "
import asyncio
from app.config import load_settings
from app.reliability.stale_tick_recovery import reconcile_stale_pipeline_ticks
print(asyncio.run(reconcile_stale_pipeline_ticks(load_settings(), source='manual')))
"
```

## SQLite restore

```bash
bash scripts/stop_local_newsroom.sh
cp var/runtime/backups/newsroom_YYYYMMDD*.db data/newsroom.db
bash scripts/start_mac_bot.sh
```

## Telethon session

- Backup: copy `TELETHON_SESSION_STRING` from secure store  
- Never commit session to git  
- Re-import via `tools/import_session_to_env.py` if invalidated

## Media cache cleanup

```bash
find var/runtime/media_cache -type f -mtime +14 -delete
```

## Verify recovery

```bash
make burnin-check
make golden-check
make public-go-check
```
