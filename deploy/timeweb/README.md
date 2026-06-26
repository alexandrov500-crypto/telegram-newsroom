# Timeweb VPS production deployment

Target: **Ubuntu 24.04** on Timeweb Cloud (example host `213.171.3.133`, `kvmnvm-449`).

Runtime: **`/entrypoint.sh`** (dirs + writable `/data`) → **`python -m app.main`** (APScheduler + aiogram + Telethon + SQLite). App rules only in Python.

## Production folder structure

```
deploy/timeweb/
├── Dockerfile              # slim, non-root, tini, layered COPY
├── docker-compose.yml      # newsroom service, volumes, healthcheck
├── .env.example            # copy → .env on VPS
├── Makefile                # up | down | logs | rebuild | restart | shell
├── README.md               # this file
└── scripts/
    └── vps-bootstrap.sh    # Docker install on Ubuntu 24.04

# On VPS after clone (operator-created, not in git):
/opt/newsroom/
├── data/ logs/ sessions/   # bind mounts (uid 1000)
└── deploy/timeweb/.env     # secrets
```

Host bind mounts (default under `/opt/newsroom`):

| Host path | Container | Contents |
|-----------|-----------|----------|
| `data/` | `/data` | SQLite DB, runtime JSON, backups |
| `logs/` | `/data/logs` | optional file logs / exports |
| `sessions/` | `/data/sessions` | Telethon `.session` file |

Application logs go to **stdout** (Docker `json-file` driver with rotation in compose).

## Quick start on VPS

**Полный пошаговый гайд (новичок):** [DEPLOY_WALKTHROUGH.md](./DEPLOY_WALKTHROUGH.md) — `213.171.3.133`, `/opt/newsroom`, bootstrap, rollback, troubleshooting.

**GitHub + Actions:** [GITHUB_DEPLOY_SETUP.md](./GITHUB_DEPLOY_SETUP.md) — git push, secrets, CI deploy, update workflow.

```bash
# 1) Bootstrap (once, as root) — or follow DEPLOY_WALKTHROUGH.md
sudo bash deploy/timeweb/scripts/vps-bootstrap.sh

# 2) Deploy user + app dir
sudo adduser --disabled-password --gecos "" newsroom
sudo usermod -aG docker newsroom
sudo mkdir -p /opt/newsroom/{data,logs,sessions}
sudo chown -R 1000:1000 /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
sudo chown newsroom:newsroom /opt/newsroom

sudo -u newsroom bash -lc '
  cd /opt/newsroom
  git clone https://github.com/YOUR_ORG/YOUR_REPO.git .
  cp deploy/timeweb/.env.example deploy/timeweb/.env
  cd deploy/timeweb && make up
'

# 3) Verify
docker compose -f deploy/timeweb/docker-compose.yml ps
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/ready | head -c 500
make -C deploy/timeweb logs
```

## Makefile commands

| Command | Action |
|---------|--------|
| `make up` | `docker compose up -d --build` |
| `make down` | stop and remove containers |
| `make logs` | follow last 200 lines |
| `make rebuild` | no-cache build + up |
| `make restart` | restart newsroom service |
| `make shell` | `exec` shell in container |
| `make gen-session` | interactive Telethon login → updates `deploy/timeweb/.env` |
| `make health` | run `docker/healthcheck.py` (+ readiness) |
| `make env-local` | build `deploy/timeweb/.env` from repo-root `.env` (Mac) |
| `make go-live` | rebuild, start, wait for first tick, classify ACTIVE/IDLE/BROKEN |
| `make go-live-verify` | log + `/runtime/status` classification only |

### GO-LIVE (VPS)

```bash
cd /opt/newsroom
git pull
cd deploy/timeweb
# ensure .env has RUNTIME_OPERATIONAL_MODE=production, DRY_RUN=false, TELETHON_SESSION_STRING or session file
bash scripts/production-deploy.sh
# or: make go-live
```

Expect `CLASSIFICATION: ACTIVE` or `PARTIAL` (ticks without publish yet). `BROKEN` → check logs for `operational_mode=` or startup validation.

### Verify pipeline is alive (30 seconds)

```bash
bash deploy/timeweb/scripts/verify-pipeline-alive.sh
```

Expect `Scheduler started`, `pipeline execution started`, and `/runtime/status` → `pipeline.likely_stalled: false`.

Production `.env` must include `RUNTIME_OPERATIONAL_MODE=production` (overrides stale `recovery` in `/data/runtime/operational_mode.json`).

### Telethon session inside Docker

`gen_session.py` is baked into the image at `/app/gen_session.py`. Compose mounts `deploy/timeweb/.env` → `/app/.env` so `--write-env` persists on the host.

```bash
cd /opt/newsroom/deploy/timeweb
cp .env.example .env   # once
make gen-session
# or: docker compose run --rm -it newsroom python gen_session.py --write-env
docker compose run --rm -it newsroom python gen_session.py --verify
make rebuild   # pick up new TELETHON_SESSION_* in running service
```

## Production logging

1. **Structured events** — use existing `utils.structured_log.log_event` for operational JSON suffixes; keep `LOG_LEVEL=INFO` in production.
2. **stdout/stderr** — `utils.logging_config.setup_logging` writes to stdout; Docker captures both streams.
3. **Rotation** — compose `logging.options.max-size` / `max-file` (20m × 5). On host: systemd timer `newsroom-docker-prune.timer` (daily 04:30 UTC) runs `deploy/timeweb/scripts/docker-prune.sh` — build cache + unused images; volumes are never pruned. Install: `sudo bash deploy/timeweb/scripts/install-docker-prune-timer.sh`.
4. **Field caps** — `LOG_MAX_FIELD_LEN=480` limits Telethon/HTTP noise in structured fields.
5. **File logs (optional)** — mount `/data/logs`; for bot-side `RotatingFileHandler`, point paths under `/data/logs` only if you enable that subsystem; default `app.main` stays stdout-first.

## Healthcheck strategy

| Layer | Check | Mechanism |
|-------|--------|-----------|
| **Liveness** | process up | Docker `HEALTHCHECK` → `docker/healthcheck.py` (env + DB `SELECT 1`) |
| **Readiness** | DB, queues, worker heartbeats | HTTP `GET /ready` on `HEALTH_HTTP_PORT` (same process as scheduler/bot) |
| **Bot / scheduler** | implicit when `/ready` ok | `gather_runtime_health` in running `app.main` (DB, optional Redis, queue depths, worker heartbeat ages) |
| **External** | optional | `curl http://127.0.0.1:8080/ready` from host (port bound to localhost in `.env.example`) |

`start_period: 120s` allows Telethon session + first scheduler tick.

## Graceful shutdown

1. **SIGTERM** — Docker sends SIGTERM; `tini` forwards to `python -m app.main`.
2. **aiogram** — `handle_signals=True` in polling; `finally` calls `lifecycle.graceful_shutdown`.
3. **APScheduler** — `scheduler.shutdown(wait=True)` with 25s timeout, then force.
4. **SQLite** — `close_db()` after job queue / Redis cleanup.
5. **Telethon** — `shutdown_collector_runtime()` disconnects collector hooks.
6. **Compose** — `stop_grace_period: 45s` aligns with shutdown budget.

Do not `kill -9` unless hung after grace period.

## Security (VPS)

### UFW

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
# Do NOT expose 8080 publicly; compose binds 127.0.0.1:8080
sudo ufw enable
sudo ufw status verbose
```

### fail2ban

```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

### SSH hardening (`/etc/ssh/sshd_config.d/99-hardening.conf`)

- `PermitRootLogin no`
- `PasswordAuthentication no` (after key-based login works)
- `MaxAuthTries 3`
- Optional: `AllowUsers newsroom` + non-default port

Reload: `sudo systemctl reload sshd`.

### Docker

- Run as non-root **inside** image (`appuser` uid 1000).
- No `--privileged`; no host network mode.
- Secrets only in `.env` on host (mode `600`), never in image layers.
- Pin image tag in production; rebuild on security patches.
- `docker compose` from `deploy/timeweb` only.

## GitHub Actions

Workflow `.github/workflows/deploy-timeweb-vps.yml` — manual deploy via SSH (secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_DIR`).

## Related project files

- `deploy/example.env.production-lite` — full variable reference
- `deploy/docker-compose.production-lite.yml` — alternate compose (repo root `.env`)
- Root `Dockerfile` — same layout, usable without Timeweb pack
