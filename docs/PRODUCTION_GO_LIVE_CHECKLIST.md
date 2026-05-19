# Production go-live checklist

## Pre-flight

- [ ] `PRODUCTION_SAFETY_ENABLED=true`
- [ ] `RELIABILITY_LAYER_ENABLED=true`
- [ ] `PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW` (start here)
- [ ] `RELIABILITY_PUBLISH_MODE=SHADOW`
- [ ] `PRODUCTION_DAILY_BUDGET_USD` set to business cap
- [ ] `ADMIN_USER_IDS` includes all operators
- [ ] `PRODUCTION_CHANNEL_WHITELIST` configured before LIMITED_CHANNELS
- [ ] Burn-in 24h+ with no FATAL incidents

## Validation

- [ ] `curl :8080/safety` → `publish_allowed` matches intent
- [ ] `curl :8080/reliability` → `overall_state: HEALTHY`
- [ ] `/safety_status` in Telegram
- [ ] `/operators_live` — no silent operators
- [ ] Prometheus: `runtime_health_score`, `telegram_floodwait_total`

## Staged promotion

1. `INTERNAL_SHADOW` — 48h observation
2. `LIMITED_CHANNELS` + whitelist — bounded publishes with approval
3. `LOW_FREQUENCY_PUBLIC` — 72h
4. `NORMAL_PRODUCTION` — set `RELIABILITY_PUBLISH_MODE=LIMITED_PRODUCTION` first
5. `FULL_PRODUCTION` only after stability window + sign-off

## Rollback (any time)

```text
/rollout_rollback
/publish_pause
```

Set env `PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW` and restart operator node.
