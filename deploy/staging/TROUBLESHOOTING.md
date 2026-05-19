# Staging troubleshooting

## Bot exits on startup (STAGING_STRICT_STARTUP)

The process prints `STARTUP FAILED — <subsystem>` with remediation hints.

| Subsystem | Check |
|-----------|--------|
| `environment` | `python3 -m bot.operations.cli validate-env` |
| `telegram_connectivity` | Bot in operator chat; admin+post on digest channel; inline keyboards allowed |
| `startup_validation` | `python3 -m bot.operations.cli validate-startup` |

Structured JSON is logged as `event=startup_failure_diagnostics`. Fix listed env vars first, then re-run:

```bash
bash scripts/ensure_staging_env.sh   # merge missing keys from example
python3 -m bot.operations.cli validate-env
```

## Health checks fail

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `/health` timeout | Bot not running or wrong port | Set `HEALTH_HTTP_PORT=8080`, start `python -m bot.main` |
| `/ready` degraded | Queue backlog without scheduler | Inspect `observability` metrics; restart ingestion |
| `/self-check` missing token | `.env` incomplete | Copy `env.staging.example`, set `TELEGRAM_BOT_TOKEN` |

```bash
bash deploy/staging/health-check.sh
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/self-check | jq .
python -m bot.operations.cli smoke
```

## Docker services unhealthy

```bash
docker compose -f deploy/staging/docker-compose.staging.yml ps
docker compose -f deploy/staging/docker-compose.staging.yml logs postgres --tail 50
```

Postgres not ready: wait 10s after `bootstrap-staging.sh`, then `docker compose ... up -d` again.

## Redis / stream backlog

- Check `newsroom_queue_backlog` in Prometheus
- Verify `REDIS_URL` matches compose network
- Operator: `/triage` for deduplicated alerts

## Burn-in regressions

```bash
python -m bot.operations.cli burnin-report
```

Review `docs/BURN_IN_REPORT_AUTO.md` and Grafana burn-in panels. Regressions enqueue a single deduplicated alert.

## Epistemic drift alerts

Open `http://localhost:8080/ops/explorer/epistemic`. If confidence inflation or homogenization alerts fire, run `/contradictions_queue` and review epistemic commands.

## Incident export

```bash
python -m bot.operations.cli incident-export my-incident-key --out var/incidents
```

Or Telegram: `/incident my-incident-key`

## Rolling restart validation

1. `docker compose ... restart`
2. `bash deploy/staging/smoke-test.sh`
3. `bash deploy/staging/validate-staging.sh`
4. Confirm burn-in run resumes (same `run_id` in `/ops/`)

## Production promotion blocked

```bash
python -m bot.operations.cli nightly-cert
```

Staging score must be ≥ 0.75 and certification must pass. See `docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`.
