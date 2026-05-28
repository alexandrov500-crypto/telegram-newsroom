# Backup & restore

## Automatic

- **Startup:** `BACKUP_ON_STARTUP=true` → `var/runtime/backups/newsroom_*.db`
- **Shutdown:** SQLite backup + WAL checkpoint on graceful stop
- **Pipeline:** scheduled backup via `scripts/backup-sqlite.sh`

## VPS host layout

```
/opt/newsroom/
  data/newsroom.db      # primary SQLite
  data/runtime/backups/ # rotated DB copies
  backups/              # optional host-level mirror
```

## Manual backup (VPS)

```bash
cd /opt/newsroom/app
docker compose -f deploy/timeweb/docker-compose.yml exec -T newsroom bash scripts/backup-sqlite.sh
```

## Restore

```bash
bash deploy/backup/restore.sh /opt/newsroom/data/runtime/backups/newsroom_YYYYMMDDTHHMMSSZ.db
```

## Telethon session

Back up `/opt/newsroom/sessions` or `TELETHON_SESSION_STRING` in secure vault — not in git.
