# Autonomous runtime operations

Unattended 3–7 day burn-in before controlled public exposure.

**VPS is the production runtime.** Local Mac: development and tests only — see [VPS_DEPLOYMENT.md](../VPS_DEPLOYMENT.md), [SERVER_OPERATIONS.md](../SERVER_OPERATIONS.md), [CURSOR_PERFORMANCE.md](../CURSOR_PERFORMANCE.md).

## Daily operator (10 min)

```bash
make ops-status          # health + runtime_report.json + public-go-check
make burnin-check        # deterministic tick contract
make golden-check        # last golden tick + publishes
bash scripts/backup-sqlite.sh
```

## Health endpoints

| Path | Checks |
|------|--------|
| `/health` | Aggregate dependency health |
| `/health/components` | runtime + pipeline + telegram + openai |
| `/health/runtime` | lease, running/stale ticks |
| `/health/pipeline` | last tick, 24h draft/reject rates |
| `/health/telegram` | polling / connectivity |
| `/health/openai` | degraded / fallback tier |

## Autonomous publish (optional)

```bash
AUTO_APPROVE_DRAFTS=true
AUTO_PUBLISH_ENABLED=true
AUTO_PUBLISH_MIN_CONFIDENCE=0.72
AUTO_PUBLISH_ALLOWED_CATEGORIES=markets,breaking,news
AUTO_PUBLISH_MIN_TEXT_CHARS=80
```

Logs: `auto_publish_approved`, `auto_publish_rejected`, `operator_review_required`.

**Default:** off during `FINAL_STAGING_MODE` unless `AUTO_PUBLISH_ENABLED=true`.

## Degradation ladder

1. Primary OpenAI summarizer  
2. `rule_fallback` / starvation fallback  
3. Branded media fallback card  
4. Text-only publish (never blocks terminal state)

## VPS deployment

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
curl -s http://127.0.0.1:8080/health/components | python3 -m json.tool
```

See also: [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md), [RECOVERY_PLAYBOOK.md](RECOVERY_PLAYBOOK.md), [PUBLISH_POLICY.md](PUBLISH_POLICY.md).

## PUBLIC GO gate

```bash
make public-go-check   # exit 0 = PASS, 2 = CONDITIONAL, 1 = FAIL
```

Requires: no `aborted_draft`, no stale running ticks, `committed_draft` + publish in 24h window, burn-in tail streak ≥3.
