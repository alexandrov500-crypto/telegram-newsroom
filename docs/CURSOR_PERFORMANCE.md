# Cursor performance — local development workstation

The newsroom runtime generates **high filesystem churn** (logs, SQLite WAL, media cache, `var/runtime`). Indexing those paths slows Cursor semantic search and AI context.

## Required: `.cursorignore`

This repo includes a production-grade `.cursorignore` at the root. After changes:

1. **Reload window** (Cmd+Shift+P → “Developer: Reload Window”)
2. Confirm `logs/`, `var/`, `data/*.db` are not opened in AI context

## Recommended Cursor settings

In Cursor / VS Code settings (`settings.json`):

```json
{
  "files.watcherExclude": {
    "**/var/**": true,
    "**/logs/**": true,
    "**/data/**": true,
    "**/.venv/**": true,
    "**/media_cache/**": true,
    "**/__pycache__/**": true
  },
  "search.exclude": {
    "**/var": true,
    "**/logs": true,
    "**/data": true,
    "**/node_modules": true
  },
  "files.exclude": {
    "**/__pycache__": true
  }
}
```

Enable **“Use Ignore Files”** for AI features so `.cursorignore` and `.gitignore` apply.

## Workspace strategy

| Mode | Where runtime runs | Local disk impact |
|------|-------------------|-------------------|
| **Production burn-in** | VPS (`deploy/timeweb/`) | Minimal — edit code only |
| **Local debug** | Mac, short sessions | High — use only when necessary |
| **Tests** | `pytest` only | Low |

Set in local `.env` when VPS owns production:

```bash
NEWSROOM_RUNTIME_PROFILE=vps
LOCAL_RUNTIME_ALLOWED=false
```

Then use `scripts/dev_start.sh` (tests) instead of `scripts/start_mac_bot.sh`.

## What to avoid locally

- Long-running `python -m app.main` during normal development
- Opening multi‑MB log files in editor
- Committing `var/`, `logs/`, `data/*.db` (already gitignored)

## Remote workflow

```bash
# From Mac — status / logs / burn-in on VPS
export VPS_HOST=your.server.ip
export VPS_USER=ubuntu
make server-status
make server-logs
```

See [VPS_DEPLOYMENT.md](VPS_DEPLOYMENT.md) and [SERVER_OPERATIONS.md](SERVER_OPERATIONS.md).
