# Self-hosting (production-lite)

This stack targets a **single VPS** or a **small Docker Compose** deployment — no Kubernetes requirement.

## Prerequisites

- Python 3.12+ (project tested on 3.12; newer interpreters may work). For a step-by-step local setup see **[docs/QUICKSTART.md](QUICKSTART.md)**.
- SQLite file on persistent disk **or** PostgreSQL (`DATABASE_URL` async URL)
- Optional Redis for cross-process queues and publish locks (`REDIS_ENABLED=true`)
- Outbound HTTPS (OpenAI) and Telegram (Bot API + Telethon)

## Minimal paths

1. Clone the repo and run `bash deploy/bootstrap.sh` (creates `var/runtime`, `var/backups`, `var/log`, quick env scan).
2. Copy `.env.example` → `.env` and fill secrets (`OPENAI_API_KEY`, `BOT_TOKEN`, Telethon session, `SOURCE_CHANNELS`, …).
3. `pip install -r requirements.txt`
4. Run DB migrations when not using auto-create path: `alembic upgrade head` (see `docs/ALEMBIC_POSTGRES.md` for Postgres).
5. `python -m app.main` (scheduler + bot) **or** split workers: `python -m workers.ingest_worker`, `ai_worker`, `publisher_worker` as documented in `docs/WORKER_RUNTIME.md`.

## Profiles

`APP_DEPLOYMENT_PROFILE` / `NEWSROOM_PROFILE`: `development` | `staging` | `production` — adjusts conservative defaults in `app/config.py` (cadence, delays, diagnostics intervals).

## Safe first boot

- Set `DRY_RUN=true` until editorial flow is verified.
- Optional `NEWSROOM_SAFE_MODE=true`: logs a caution banner at startup (`startup_validation`); combine with `DRY_RUN` for paper mode.
- `python -m tools.admin_cli config-doctor` prints a **non-secret** summary after `.env` is valid.
- `python -m tools.admin_cli runtime-integrity-check` validates JSON under `RUNTIME_STATE_DIR`.

## HTTP health

With `HEALTH_HTTP_PORT>0`: `/health`, `/ready`, optional `/ops` (see `docs/WEB_ADMIN.md`). Protect ops endpoints with `OPS_HTTP_TOKEN` when exposed beyond localhost.

## Version metadata

`app/versioning.py` exposes `app_version` and schema compatibility integers surfaced in startup logs (`lifecycle.log_startup_structured`).
