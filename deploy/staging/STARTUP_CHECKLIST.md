# Staging startup checklist

## Before start

- [ ] `.env` from `env.staging.example` with secrets filled
- [ ] `TELEGRAM_BOT_TOKEN` valid
- [ ] `TELEGRAM_DIGEST_CHANNEL_ID` — bot is admin with post rights
- [ ] `TELEGRAM_OPERATOR_CHAT_ID` — bot can message operators
- [ ] `PRODUCTION_CHANNEL_BLOCKLIST` lists live production channel IDs
- [ ] `STAGING_MODE=true`, `SHADOW_PUBLISH_ONLY=true`, `AUTO_APPROVAL_ENABLED=false`

## Infrastructure

```bash
bash deploy/staging/bootstrap-staging.sh
docker compose -f deploy/staging/docker-compose.staging.yml ps
```

- [ ] postgres healthy
- [ ] redis up
- [ ] prometheus :9090
- [ ] grafana :3000
- [ ] tempo :4317

## Activation

```bash
bash scripts/staging_activate.sh
```

Or operator container only:

```bash
docker compose -f deploy/staging/docker-compose.staging.yml up -d operator
```

## Verify (first 15 minutes)

- [ ] `python3 -m bot.operations.cli validate-env` → PASS
- [ ] `bash deploy/staging/health-check.sh` → all required endpoints
- [ ] `curl http://localhost:8080/health` → ok
- [ ] `curl http://localhost:8080/startup` → `"passed": true`
- [ ] `curl http://localhost:8080/self-check` → ok
- [ ] `python3 -m bot.operations.cli validate-startup` → PASS
- [ ] Logs contain `[STARTUP OK]` with telegram/redis/postgres/feeds/operator_console/burnin
- [ ] Prometheus `startup_validation_passed` = 1
- [ ] Logs: `event=telegram_connectivity` → READY
- [ ] Logs: `event=burnin_auto_started profile=24h`
- [ ] RSS: `event=ingestion_cycle_start feed_count>0`
- [ ] Grafana staging-readiness panels updating
- [ ] `/ops/` explorers load

## 24h burn-in

- [ ] `docs/BURN_IN_REPORT.md` updated after first report tick
- [ ] `python3 -m bot.operations.cli burnin-report`
- [ ] Operator `/dashboard` workload acceptable
- [ ] No production channel publishes (audit table only staging IDs)

## Rollback

See `docs/PRODUCTION_ROLLBACK.md` and `TROUBLESHOOTING.md`.
