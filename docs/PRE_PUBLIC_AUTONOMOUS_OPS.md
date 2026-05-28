# Pre-public autonomous operations (hub)

Single index for **VPS burn-in** + **local dev** split.

| Doc | Topic |
|-----|--------|
| [CURSOR_PERFORMANCE.md](CURSOR_PERFORMANCE.md) | `.cursorignore`, IDE settings |
| [VPS_DEPLOYMENT.md](VPS_DEPLOYMENT.md) | Move runtime to server |
| [SERVER_OPERATIONS.md](SERVER_OPERATIONS.md) | `make server-*` commands |
| [operations/AUTONOMOUS_RUNTIME.md](operations/AUTONOMOUS_RUNTIME.md) | Daily burn-in checklist |
| [operations/RECOVERY_PLAYBOOK.md](operations/RECOVERY_PLAYBOOK.md) | Restart, stale ticks, DB restore |
| [operations/INCIDENT_RESPONSE.md](operations/INCIDENT_RESPONSE.md) | Incidents |
| [PREPUBLIC_CHECKLIST.md](PREPUBLIC_CHECKLIST.md) | Sign-off |

## Architecture

```
Mac (dev)                    VPS (24/7)
─────────                    ──────────
Cursor + pytest              Docker newsroom
No app.main loop             Scheduler + Telethon + publish
.cursorignore                /opt/newsroom/data persistent
```

## Mac `.env` after migration

```bash
NEWSROOM_RUNTIME_PROFILE=vps
LOCAL_RUNTIME_ALLOWED=false
VPS_HOST=203.0.113.10
VPS_USER=ubuntu
```

## Daily (from Mac)

```bash
make server-status
make server-burnin    # burnin-report alias
make public-go-check
```

## One-time migration

```bash
bash scripts/stop_local_newsroom.sh
bash scripts/migrate_to_vps.sh   # checklist helper
# On VPS: deploy/timeweb → make up
```
