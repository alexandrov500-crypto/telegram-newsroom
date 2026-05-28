# Server operations (VPS)

Operator commands for the autonomous runtime. Assumes `deploy/timeweb/` on the server.

## Environment (Mac shell)

```bash
export VPS_HOST=203.0.113.10
export VPS_USER=ubuntu
export VPS_DEPLOY_DIR=/opt/newsroom/app/deploy/timeweb
```

## Make targets (from repo root on Mac)

| Command | Action |
|---------|--------|
| `make server-status` | Health + runtime report on VPS |
| `make server-logs` | `docker compose logs -f` |
| `make runtime-health` | `/health/components` JSON |
| `make restart-runtime` | `compose restart` |
| `make server-burnin` | `burnin-check` on VPS |
| `make server-backup` | SQLite backup on VPS |

## On-server (SSH)

```bash
cd /opt/newsroom/app/deploy/timeweb
make health          # curl local health
make logs
make restart
make down && make up # full recreate
```

## Health endpoints

```bash
curl -s http://127.0.0.1:8080/health/components | jq .
curl -s http://127.0.0.1:8080/health/pipeline | jq .
curl -s http://127.0.0.1:8080/health/telegram | jq .
curl -s http://127.0.0.1:8080/health/openai | jq .
```

## Log rotation

Docker logging: `json-file` max 20m × 5 files (see `docker-compose.yml`).

Host logrotate example: `deploy/logrotate/newsroom.conf`

## Maintenance

```bash
# Media cache >14d
find /opt/newsroom/data/runtime/media_cache -type f -mtime +14 -delete

# SQLite backup (also on startup)
bash /opt/newsroom/app/scripts/backup-sqlite.sh
```

## Telegram session

- Persist `TELETHON_SESSION_STRING` in VPS `.env` (not in git)  
- Or volume ` /opt/newsroom/sessions`  
- Re-auth: `make gen-session` in timeweb Makefile (see `TELEGRAM_CREDENTIALS.md`)

## Local vs VPS

| Task | Where |
|------|--------|
| Edit Python | Mac |
| `pytest` | Mac (`scripts/dev_start.sh`) |
| 24/7 pipeline | VPS only |
| Burn-in | VPS |
| Cursor indexing | Mac — use `.cursorignore` |
