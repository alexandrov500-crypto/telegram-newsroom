# Persistent staging runtime

24/7 staging stack for real-world validation: RSS ingestion, multilingual feeds, Telegram channels, Redis Streams, PostgreSQL, Prometheus, Grafana, and Tempo/Jaeger tracing.

## Quick start (real-world activation)

```bash
cp deploy/staging/env.staging.example .env
# Required: TELEGRAM_BOT_TOKEN, TELEGRAM_DIGEST_CHANNEL_ID, TELEGRAM_OPERATOR_CHAT_ID
# Optional: PRODUCTION_CHANNEL_BLOCKLIST (comma-separated production channel IDs)

bash scripts/staging_activate.sh
```

Or manually:

```bash
export STAGING_MODE=true SHADOW_PUBLISH_ONLY=true AUTO_APPROVAL_ENABLED=false
export OPS_BURNIN_ENABLED=true OPS_BURNIN_PROFILE=24h STAGING_STRICT_STARTUP=true
bash deploy/staging/bootstrap-staging.sh
python3 -m bot.main   # operator node, health :8080
```

See [STARTUP_CHECKLIST.md](./STARTUP_CHECKLIST.md) for the full operator checklist.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Bot health | 8080 | `/health`, `/ready`, `/self-check`, `/ops/` explorers |
| Grafana | 3000 | `staging-readiness` dashboard |
| Prometheus | 9090 | Metrics scrape |
| Tempo | 3200 | Trace backend |
| PostgreSQL | 5432 | Durable state |
| Redis | 6379 | Streams / coordination |

## Automated checks

- **Startup**: `GET /startup` — full deterministic validation report; `GET /self-check` — summary
- **CLI**: `python3 -m bot.operations.cli validate-startup`
- **Telegram**: `/staging_status` (operator node)
- **Smoke**: `bash deploy/staging/smoke-test.sh`
- **Staging validation**: `python -m bot.operations.cli validate-staging`
- **Burn-in**: auto-starts 7d when `OPS_BURNIN_ENABLED=true`
- **Reports**: `python -m bot.operations.cli burnin-report` → `docs/BURN_IN_REPORT_AUTO.md`

## Operator onboarding

1. Open Grafana → staging-readiness dashboard
2. Open `http://localhost:8080/ops/` for replay, contradictions, epistemic drift
3. Telegram admin commands: `/ops`, `/dashboard`, `/triage`, `/session`, `/incident`
4. **Live operator console** (`TELEGRAM_LIVE_INGEST_ENABLED=true`): severity-routed signals, aggregated contradiction/ingest bursts, fatigue-aware digest mode, smart approval batches, incident threads, 30m ops digests; `/ops_score`, `/approval_queue`, `/incident_thread`, `/inspect_replay`, `/ops_usability`
5. Nightly: `bash scripts/nightly_cert.sh` (cron-friendly)

## Unattended operation

- Rolling restart: `docker compose -f deploy/staging/docker-compose.staging.yml restart`
- Re-run `validate-staging.sh` after restart
- Burn-in and epistemic snapshots run on the 180s operations tick
- Alert deduplication prevents operator fatigue during long runs

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for failure recovery.
