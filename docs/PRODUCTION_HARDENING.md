# Production hardening — editorial operating system

## Control plane vs worker

| Surface | MacBook (control) | VPS (worker) |
|---------|-------------------|--------------|
| Cursor / git | yes | deploy target |
| `newsroom` CLI | yes | optional SSH |
| Telegram polling | **no** | **yes** |
| APScheduler pipeline | optional dry-run | **yes** |
| Publishing | via CLI → worker API | **yes** |
| Health HTTP | local `:8080` | `:8080` (bind 127.0.0.1) |

**Rule:** one `BOT_TOKEN` → one poller. Cross-host enforcement uses `RUNTIME_NODE_ROLE` (not shared filesystem locks).

## Runtime ownership model

1. **Local singleton** (`app/ops/runtime/singleton_guard.py`) — one process per machine.
2. **Leadership leases** (`ops/resilience/leadership.py`) — runtime / scheduler / publish file locks on worker.
3. **Node role** (`app/ops/runtime/node_role.py`) — `worker` vs `control` disables polling & pipeline on Mac.
4. **Execution lease** (`app/ops/runtime/execution_lease.py`) — SQLite row when using shared `DATABASE_URL` (optional); records intended worker hostname.
5. **Telegram** — last line of defence; conflicts → `telegram.polling.conflict` in logs.

### Environment

```bash
# VPS deploy/timeweb/.env
RUNTIME_NODE_ROLE=worker
TELEGRAM_POLLING_ENABLED=true

# Mac .env (management)
RUNTIME_NODE_ROLE=control
TELEGRAM_POLLING_ENABLED=false
NEWSROOM_WORKER_URL=http://213.171.3.133:8080   # optional, for CLI remote status
```

### Operator commands

```bash
make newsroom-status      # local + remote worker
make newsroom-diagnose
make newsroom-logs

# On VPS only (worker):
docker compose up -d newsroom

# Mac takeover (stop VPS first):
docker stop telegram-newsroom   # on VPS
RUNTIME_NODE_ROLE=worker make mac-start
```

## Failure scenarios

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| Mac + VPS both poll | `/health` → `conflict_detected` | `docker stop telegram-newsroom` or Mac `RUNTIME_NODE_ROLE=control` |
| Pipeline stuck | `pipeline.likely_stalled` in `/runtime/status` | restart worker; check Telethon logs |
| Desk rejects all | `pipeline.idle` + `desk_reject:*` | lower `DESK_*` thresholds or fix sources |
| OpenAI circuit open | `/runtime/circuit` | fix key; wait half-open; restart |
| DB locked | SQLite locked runbook | single writer; stop duplicate process |

## Deploy (one command)

```bash
cd deploy/timeweb
bash scripts/production-deploy.sh   # preflight, backup, up, health
```

Rollback: restore `.env` + `data/` backup from deploy script; `docker compose up -d`.

## Monitoring

- **Liveness:** `GET /health` (aggregate)
- **Readiness:** `GET /ready` (DB + deps, no OpenAI probe)
- **Operator:** `GET /runtime/status`, `GET /ops/dashboard/overview`
- **Panel:** `GET /ops/panel` (HTML)
- **Metrics:** `GET /metrics` (Prometheus text)

## Phased rollout

| Phase | Scope | Status |
|-------|--------|--------|
| P0 | Node role, Mac CLI, docs | this PR |
| P1 | Execution lease table + `/live` | partial |
| P2 | DLQ / failed-draft retry UI | existing publish journal |
| P3 | Redis optional global lock | if `REDIS_ENABLED=true` |

## What we deliberately did not add

- Kubernetes, multi-region, heavy message buses
- New AI features (separate editorial track)

---

## Full hardening map (10 areas)

| # | Area | Implementation today | Next (optional) |
|---|------|----------------------|-------------------|
| 1 | Runtime ownership | `RUNTIME_NODE_ROLE`, `execution_lease.json`, `execution_intent.json`, singleton flock | Shared DB lease when Mac uses remote SQLite |
| 2 | Supervisor | APScheduler listeners, `run_operational_heartbeat`, lane workers, leadership locks | Stuck-tick auto-resume job |
| 3 | Dashboard | `/ops`, `/ops/dashboard/overview`, `/runtime/status` | HTMX panel alias `/ops/panel` → `/ops` |
| 4 | Structured logs | `utils/structured_log`, `log_event`, rotating file logs | Enforce `correlation_id` on all publish paths |
| 5 | Self-healing | DLQ in `/ops/dlq`, publish journal, `retry-failed` via admin | Auto-retry cron on worker |
| 6 | Health | `/health`, `/ready`, `/live`, `/metrics` | Aggregate `critical` tier doc in runbook |
| 7 | Mac CLI | `scripts/newsroom`, `make newsroom-status` | `restart` via systemd/compose SSH |
| 8 | Deploy | `deploy/timeweb/scripts/production-deploy.sh` | Pre-push hook only |
| 9 | AI safety | `editorial_safety_enabled`, desk filter, dedupe | Source-agreement scorer |
| 10 | Editorial memory | reputation, diversity, dedupe window | Topic fatigue JSON store |

## Operator workflow (daily)

1. **Morning:** `make newsroom-status` (Mac) — local + `NEWSROOM_WORKER_URL` if set.
2. **Moderation:** Telegram admin bot on the machine that holds `RUNTIME_NODE_ROLE=worker`.
3. **Deploy:** VPS only — `production-deploy.sh`; Mac stays `control`.
4. **Incident:** `make newsroom-diagnose` → if `conflict_detected` → stop duplicate poller.
5. **Failover:** `make newsroom-takeover` → stop VPS container → Mac `RUNTIME_NODE_ROLE=worker` → `make mac-start`.

## Rollback

1. `docker compose` previous image tag on VPS.
2. Restore `data/` + `.env` from deploy backup directory.
3. `curl /health` until `healthy` and `conflict_detected=false`.

## Monitoring strategy

- **Synthetic:** cron on Mac `curl -sf $NEWSROOM_WORKER_URL/health`.
- **Logs:** `make newsroom-logs` or `tail -f logs/local-run.log`.
- **Metrics:** scrape `:8080/metrics` (token if `OPS_HTTP_TOKEN` set).
- **Alerts (manual):** Telegram conflict, OpenAI circuit open, `pipeline.likely_stalled` in `/runtime/status`.
