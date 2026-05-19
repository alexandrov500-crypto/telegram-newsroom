# Production reliability checklist

## Pre-production

- [ ] `RELIABILITY_LAYER_ENABLED=true` on operator node
- [ ] `RELIABILITY_PUBLISH_MODE=SHADOW` (or `DRY_RUN` for paper trading)
- [ ] Burn-in 24h with `RELIABILITY_BURNIN_MODE=true`
- [ ] `GET /reliability` returns `overall_state: HEALTHY`
- [ ] Prometheus `runtime_health_score` ≥ 0.8 sustained

## Operator Telegram

- [ ] `/health_live` — all subsystems green
- [ ] `/queues_live` — publish gate shows SHADOW/blocked as expected
- [ ] `/incidents_live` — empty or acknowledged
- [ ] `/recovery_live` — no exhausted recovery keys
- [ ] Daily ops digest received

## Publishing transition

- [ ] 1h+ stable health, zero FATAL incidents
- [ ] Switch `RELIABILITY_PUBLISH_MODE=LIMITED_PRODUCTION`
- [ ] Verify operator approval still required per item
- [ ] Monitor `staging_shadow_publish_total` vs production counters
- [ ] Full production only after `PUBLISH_STABILITY_SEC` satisfied

## Post-deploy monitoring

- [ ] Grafana staging-readiness + `runtime_health_score`
- [ ] Alert on `reliability_degraded_mode=1` > 15m
- [ ] Weekly review `docs/BURN_IN_REPORT_AUTO.md`
