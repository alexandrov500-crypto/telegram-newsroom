# Deployment (production-lite)

This document describes **small-footprint** deployment patterns: single host, Docker Compose, or systemd. It is **not** a Kubernetes/Helm/Terraform guide and makes **no cloud-specific assumptions**.

**Fast path:** [DEPLOYMENT_QUICKSTART.md](DEPLOYMENT_QUICKSTART.md) (15-minute production-lite walkthrough). **Templates:** `deploy/example.env.production-lite`, `deploy/docker-compose.production-lite.yml`, `deploy/systemd/newsroom-nightly.*`.

## Positioning

- **One writer** to a SQLite file; do not share one SQLite DB across multiple processes.
- **Optional Redis** for queues and cross-process locks; the app can start **degraded** if Redis is temporarily unavailable (see `docs/RESILIENCE_AND_FAILURE_MODES.md`).
- **Bounded** observability: structured logs, optional HTTP `/health` / `/ready` / `/ops*`, static HTML dashboards from offline bundles.

## Directory layout (recommended)

| Path | Purpose |
|------|---------|
| Repo root | Code, `tools/`, `docs/`, `Makefile`, `pyproject.toml` |
| `./var/runtime` | `RUNTIME_STATE_DIR` JSON snapshots (operational timeline, metrics, etc.) |
| `./var/reports` | Generated HTML/JSON reports (dashboard, qualification) |
| `./var/backups` | `tools/backup_cli.py` output (see `docs/BACKUP_AND_RECOVERY.md`) |
| `./data` or `/data` (container) | SQLite file + Telethon session file on persistent volume |

`deploy/bootstrap.sh` creates a sensible subset of these paths.

## Runtime state layout (`RUNTIME_STATE_DIR`)

JSON and small text artifacts used for observability and editorial intelligence (no secrets intended). Typical files include operational timeline, event history, suppression state, drift snapshots — see `utils/runtime_bundle.py` / `docs/RUNTIME_ARTIFACTS.md`.

- Keep `RUNTIME_STATE_DIR` on the **same volume** as backups if you use `backup_cli` with runtime inclusion.
- Run `python -m tools.admin_cli runtime-integrity-check` after incidents.

## Retention recommendations

- **DB retention:** `RETENTION_PROCESSED_RAW_DAYS`, `RETENTION_REJECTED_DRAFT_DAYS` in `.env` (see `README.md`).
- **Artifact retention:** `tools/runtime_retention.py` / `docs/RUNTIME_RETENTION.md` for zip + JSON roots used in CI or manual ops.
- **Logs:** configure Docker log rotation or host logrotate (`deploy/logrotate.newsroom.example`).

## Backup recommendations

- Use `python tools/backup_cli.py backup-create` — archives DB + optional runtime tree; validate with `backup-validate`. Details: `docs/BACKUP_AND_RECOVERY.md`.
- Before upgrades, take a backup and store the **git SHA** and `.env` version (out of repo).

## SQLite vs PostgreSQL

| | SQLite (default) | PostgreSQL |
|---|------------------|------------|
| Ops complexity | Low | Higher (migrations, backups, connection URL) |
| Writers | Single process recommended | Pool + multi-instance patterns possible |
| URL | `sqlite+aiosqlite:///…` | `postgresql+asyncpg://…` (see `docs/ALEMBIC_POSTGRES.md`) |

There is **no** automatic SQLite→Postgres migration in-repo; plan a logical migration if you outgrow SQLite.

## Redis optionality

- `REDIS_ENABLED=false` — in-process / degraded queue patterns (see worker docs).
- `REDIS_ENABLED=true` — set `REDIS_URL` and queue-related env vars; use healthchecks in Compose.

Example Compose with optional Redis: root `docker-compose.example.yml` (`--profile with-redis`).

## Upgrade workflow (high level)

1. Read `CHANGELOG.md` and `docs/DEPLOYMENT_UPGRADE_CHECKLIST.md`.
2. **Backup** DB + `RUNTIME_STATE_DIR`.
3. `git pull` (or deploy new image tag).
4. `pip install -r requirements.txt` or rebuild image.
5. `alembic upgrade head` when schema changes (Postgres; SQLite may auto-create on first boot depending on path).
6. Restart process with **graceful shutdown** (SIGTERM) — see `app/lifecycle.py` / systemd example.
7. Run `make runtime-preflight` and smoke tests (`make test` or targeted `pytest tests/runtime`).

## Rollback notes

- **Code:** redeploy previous git tag / image.
- **Database:** restore from `backup_cli` zip; avoid mixing Alembic revisions — downgrade only when documented safe.
- **Runtime JSON:** restore from backup or accept empty regeneration (editorial memory may reset).

## Docker (reference)

- Production-style samples live under `deploy/` (`docker-compose.prod.yml`, `docker-compose.postgres.yml`, `Dockerfile.example`).
- A **minimal** root example for local experiments: `docker-compose.example.yml` (single service + optional Redis profile).

## systemd

See `systemd/newsroom-bot.service.example` — `WorkingDirectory`, `EnvironmentFile`, restart policy, stop timeout aligned with worker grace settings.

## Related docs

- `docs/SELF_HOSTING.md` — first-boot safety.
- `docs/OPERATIONS.md` — recurring workflows.
- `docs/WORKER_RUNTIME.md` — split worker processes.
