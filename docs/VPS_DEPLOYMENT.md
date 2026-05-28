# VPS deployment — autonomous 24/7 runtime

Move **burn-in and publishing** to the server. Keep the Mac for **code + tests only**.

## Target

- Ubuntu 24.04 LTS  
- 2–4 vCPU, 4–8 GB RAM  
- Single Docker container (`deploy/timeweb/`)

## First-time setup (VPS)

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo mkdir -p /opt/newsroom/{data,logs,sessions,backups}
sudo chown -R "$USER:$USER" /opt/newsroom

git clone <repo> /opt/newsroom/app
cd /opt/newsroom/app/deploy/timeweb
cp .env.example .env
# Edit .env: BOT_TOKEN, OPENAI_*, TELEGRAM_*, TARGET_CHANNEL_ID, TELETHON_SESSION_STRING
bash scripts/build-vps-env.sh   # optional helper
make up
make health
```

Host paths (default in `docker-compose.yml`):

| Host | Container | Purpose |
|------|-----------|---------|
| `/opt/newsroom/data` | `/data` | SQLite + runtime state |
| `/opt/newsroom/logs` | `/data/logs` | Application logs |
| `/opt/newsroom/sessions` | `/data/sessions` | Telethon session files |

## Mac → VPS handoff

1. On Mac: `bash scripts/stop_local_newsroom.sh`
2. On VPS: `docker stop telegram-newsroom` only if upgrading; otherwise `make up`
3. On Mac `.env`: `NEWSROOM_RUNTIME_PROFILE=vps` and `LOCAL_RUNTIME_ALLOWED=false`
4. Verify: `curl http://VPS_IP:8080/health/components` (or SSH tunnel)

**Never run the same `BOT_TOKEN` on Mac and VPS simultaneously.**

## Compose alternatives

| Path | Use case |
|------|----------|
| `deploy/timeweb/docker-compose.yml` | **Recommended** Timeweb / generic VPS |
| `deploy/docker-compose.prod.yml` | Minimal single-volume compose |

## Bootstrap & restart safety

On container start the app:

- Reconciles **stale pipeline ticks** (`stale_tick_timeout`)
- Runs **SQLite backup** if `BACKUP_ON_STARTUP=true`
- Restores **checkpoint** / publish journal (no duplicate republish)
- Re-acquires **runtime lease**

After VPS reboot:

```bash
cd /opt/newsroom/app/deploy/timeweb && make up
make health
```

## Burn-in on VPS

```bash
# SSH to VPS, or from Mac:
make server-burnin
```

Artifacts: `/opt/newsroom/data/runtime/burnin_snapshot.json`, `runtime_report.json`

## Rollback

```bash
make down
cp /opt/newsroom/backups/newsroom_*.db /opt/newsroom/data/newsroom.db
make up
```

See [SERVER_OPERATIONS.md](SERVER_OPERATIONS.md) and [operations/RECOVERY_PLAYBOOK.md](operations/RECOVERY_PLAYBOOK.md).
