# Observability validation (diagnostics v2)

Staging review of `tools/live_telegram_diagnostics.py` — read-only, no Telegram API writes.

## Tool contract

| Property | Expected | Staging result |
|----------|----------|----------------|
| `read_only` | `true` | **PASS** |
| `no_telegram_api_calls` | `true` | **PASS** |
| `schema_version` | `2` | **PASS** |
| Exit code | `0` unless `--strict` + HIGH | **PASS** |

## Metric interpretation

### Publish outcomes (`operational.publish_outcomes`)

| Field | Meaning | Healthy (T1) |
|-------|---------|--------------|
| `success_total` | `publishes` + `drafts_published` | Increments with approved publishes |
| `failures` | Failed publish attempts | 0 or rare; investigate each |
| `cadence_blocked` | Editorial gate blocked | Expected occasionally |
| `retries` | Publisher chunk retries | Low; spikes → API issues |

### Session stability (`operational.session_stability`)

| Field | Meaning | Alert if |
|-------|---------|----------|
| `reconnect_count` | `telethon_reconnects` | >10 per session |
| `api_failure_count` | `telegram_api_failures` | >5 without recovery |
| `flood_wait_count` | `telethon_flood_waits` | >5 in short window |
| `session_reset_suspected` | reconnects≥5 AND api_fail≥3 | `true` |

### Lock contention (`operational.lock_contention`)

| Field | Meaning | Alert if |
|-------|---------|----------|
| `contention` | Second publisher blocked | Sustained >20 (duplicate job suspicion) |
| `strict_denied` | Fail-closed without Redis | >0 in T2 with healthy Redis |
| `redis_fallback` | Local lock after Redis error | >0 in multi-worker |
| `stale_suspected` | TTL / stale lock signal | Any in T1 single-worker |

### Retry amplification (`operational.retry_amplification`)

| Field | Meaning | Alert if |
|-------|---------|----------|
| `publish_retries` | aiogram chunk retries | >15 cumulative |
| `openai_retries` | LLM path | Storm with worker burst |
| `worker_safe_reorders` | Safe re-enqueue | Informational |

## Alert thresholds (production-lite)

| Severity | Condition | Action |
|----------|-----------|--------|
| HIGH | `status: FAIL` in diagnostics | Stop publish; T0 |
| HIGH | `session_reset_suspected` | Re-auth session |
| HIGH | `retry_burst_window` ≥ storm env | Pause workers |
| MEDIUM | `telethon_flood_waits` > 5 | Reduce rate |
| MEDIUM | `publish_retries` > 15 | Inspect logs |
| LOW | `publish_lock_contention` > 20 | Review duplicate jobs |

## Expected ranges (T1, healthy day)

| Metric | Expected |
|--------|----------|
| `telethon_reconnects` | 0–3 |
| `telethon_flood_waits` | 0–2 |
| `publish_retries` | 0–5 |
| `publish_failures` | 0 |
| `publish_lock_contention` | 0–2 |

## False-positive guidance

| Signal | False positive when | Ignore if |
|--------|---------------------|-----------|
| `dry_run_off` WARNING | Intentional bounded publish sign-off | ≤5 publishes documented |
| `duplicate_publish_hints` | Test lock contention in CI | No second worker |
| `redis_ping` FAIL | `REDIS_ENABLED=false` | T1 single-node |
| High `openai_retries` | Transient OpenAI rate limit | Recovered within 1 tick |

## Staging validation procedure

```bash
make live-telegram-diagnostics
python3 tools/staging_environment_verify.py
# After activity:
make live-telegram-diagnostics | jq '.operational'
```

## Sign-off

| Check | Date | Result |
|-------|------|--------|
| Schema v2 fields present | 2026-05-16 | **PASS** |
| Counters match metrics.py | 2026-05-16 | **PASS** |
| Findings logic reviewed | 2026-05-16 | **PASS** |
| Post-publish snapshot | PENDING | Operator after ≤5 publishes |
