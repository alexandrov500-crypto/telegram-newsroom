# Release Notes — v3-production-degraded-runtime

**Date:** 2026-05-20  
**Branch:** `v3-live-telegram-validation`  
**Commits:** `6be9132`, `0ffebb7` (HEAD)  
**Target:** Timeweb VPS production-lite (`213.171.3.133`)

## Summary

Production-grade autonomous Telegram newsroom runtime: self-healing polling, degraded-mode startup, operational observability, and release traceability. The process stays alive when OpenAI, Telethon, or Telegram API are partially unavailable.

## Runtime architecture (frozen baseline)

- **Startup:** config validation (fail-closed) → DB → healthchecks (fail-open for optional deps) → scheduler + resilient polling supervisor
- **Telegram:** webhook introspection → connectivity probe → infinite polling loop with exponential backoff (5→30s)
- **Dependencies:** `healthy` / `degraded` / `unavailable` registry exposed on `/health` v2
- **Observability:** `/version`, `/health`, `/ready`, `/metrics` (Prometheus), structured logs, incident bundle script

## What changed

### Resilience
- Startup healthchecks with Telegram `get_me` retry/backoff (`HEALTHCHECK_TIMEOUT_SEC`, `TELEGRAM_HTTP_TIMEOUT_SEC`)
- Degraded startup: OpenAI region block and Telethon session issues do not crash the process
- Self-healing polling supervisor (`TelegramNetworkError`, `TimeoutError`, `TelegramConflictError`)
- `TELEGRAM_POLLING_ENABLED=false` for local dev (scheduler + HTTP without polling)

### Operations
- Build provenance in Docker image (`NEWSROOM_GIT_SHA`, `BUILD_*`)
- `GET /version` release fingerprint
- Runtime counters: `polling_restarts_total`, `telegram_conflicts_total`, `telegram_network_failures_total`, `openai_failures_total`, `degraded_state_transitions_total`
- SLO env thresholds (`RUNTIME_DEGRADED_AFTER_N_FAILURES`, etc.)
- `tools/debug_telegram_runtime.sh` → incident tar.gz
- Graceful shutdown structured logs (`runtime.shutdown.started` / `completed`)

### Deploy
- `deploy/timeweb/` Docker Compose stack, `start_period: 180s`, `tini -s`
- aiogram 3.7+ `AiohttpSession` + `DefaultBotProperties`

## Production validation (2026-05-20, VPS)

| Check | Result |
|-------|--------|
| Deploy `0ffebb7` with build args | PASS |
| `/version` git_sha | `0ffebb7` (not unknown) |
| Container health | `healthy`, `restarts=0` |
| `/health` aggregate | `degraded` (expected: OpenAI + Telethon + Telegram conflict) |
| `/metrics` runtime counters | Present |
| Incident bundle | `/tmp/newsroom-incident.tar.gz` created |
| Restart | `runtime_started_at` / `polling_instance_id` refresh; `restarts=0` |
| Network flap (iptables) | SKIPPED (sudo requires password on VPS) |

### Known operational items (non-blocking for degraded runtime)
1. **TelegramConflictError** — second bot instance polling same token; stop local/dev duplicate.
2. **Telethon** — `session not authorized`; run `python gen_session.py --write-env` on trusted machine.
3. **OpenAI** — VPS region `unsupported_country_region_territory`; AI pipeline disabled until proxy/endpoint fix.
4. **`runtime_ops_state` table** — created; row persistence may be empty until first successful async persist (verify after conflict/network events).

## Upgrade / deploy

```bash
cd /opt/newsroom && git pull origin v3-live-telegram-validation
cd deploy/timeweb
export GIT_SHA=$(git -C /opt/newsroom rev-parse --short HEAD)
export BUILD_TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export BUILD_BRANCH=$(git -C /opt/newsroom rev-parse --abbrev-ref HEAD)
export BUILD_VERSION=1.0.0
docker compose build --no-cache && docker compose up -d
curl -s http://127.0.0.1:8080/version | jq
bash /opt/newsroom/tools/debug_telegram_runtime.sh /tmp/newsroom-incident.tar.gz
```

## HTTP endpoints

| Path | Purpose |
|------|---------|
| `/health` | Aggregate + dependency v2 + `runtime_slo` |
| `/version` | Build + runtime fingerprint |
| `/ready` | DB/queue readiness probe |
| `/metrics` | Prometheus exposition |

## Tag

```bash
git tag -a v3-production-degraded-runtime -m "Production degraded-runtime baseline"
git push origin v3-production-degraded-runtime
```

---

*Runtime architecture frozen at this tag before next feature work.*
