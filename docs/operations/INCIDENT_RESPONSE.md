# Incident response

## Severity

| Level | Examples | Action |
|-------|----------|--------|
| S1 | Channel spam, wrong publish, leak | Stop runtime, rollback draft |
| S2 | No publishes 12h+, stuck ticks | `make recover-runtime` pattern below |
| S3 | OpenAI 429 only | Enable fallback env, monitor |

## Immediate steps

```bash
bash scripts/stop_local_newsroom.sh
curl -s http://127.0.0.1:8080/health/components
make ops-status
sqlite3 data/newsroom.db "SELECT id,status,json_extract(detail_json,'$.terminal_state') FROM pipeline_ticks ORDER BY id DESC LIMIT 5;"
```

## Emergency pause

- Set `RUNTIME_OPERATIONAL_MODE=safe` or ops control plane halt  
- `AUTO_PUBLISH_ENABLED=false`  
- Do not delete DB without backup: `bash scripts/backup-sqlite.sh`

## Quota exhaustion

- `BURNIN_OPENAI_ALWAYS_FALLBACK=true`  
- Restore billing OR accept fallback-only burn-in  
- Verify: `grep rule_fallback logs/local-run.log | tail -5`

## Telegram outage

- Check `/health/telegram`  
- FloodWait: wait; do not restart loop rapidly  
- Idempotent publish: republish same draft should no-op (`publish.idempotent_skip`)

## Rollback publish

- Unpublish manually in channel if needed  
- Mark draft rejected in DB via bot `/reject <id>`
