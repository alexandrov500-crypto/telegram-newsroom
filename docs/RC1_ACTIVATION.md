# RC1 Stabilization & Public Activation

Release candidate `rc1-2026.05.17` — deterministic config, lockdown, activation workflow, and launch dashboard.

## Architecture

```
bot/rc1/
  config/       # Registry + validation graph
  lockdown.py   # RC1_LOCKDOWN_MODE
  profiling/    # Runtime hotspots
  baselines/    # Anomaly learning
  hardening/    # Failure-mode guards
  validation/   # Live traffic confidence
  activation/   # Stage machine
  operator/     # UX digest, dedup, quiet hours
  dashboard/    # /launch_dashboard
```

## Operator commands

| Command | Purpose |
|---------|---------|
| `/config_status` | Startup validation + fingerprint |
| `/config_diff` | Drift vs stored fingerprint |
| `/rc_status` | RC1 lockdown state |
| `/runtime_profile` | Bottleneck hotspots |
| `/activation_status` | Current activation stage |
| `/activate_next_stage` | Advance with sign-off (cert-gated) |
| `/activation_rollback` | Roll back activation + shadow rollout |
| `/launch_dashboard` | Executive go-live view |
| `/operator_digest` | Batched pending alerts |

HTTP: `GET /rc1`

## Activation stages

1. **PRECHECK** — config valid, operator sign-off  
2. **CERTIFICATION** — formal CERTIFIED state  
3. **SHADOW_TRAFFIC** — shadow-only validation  
4. **LIMITED_PUBLIC** — `LIMITED_CHANNELS` rollout  
5. **CONTROLLED_EXPANSION** — `LOW_FREQUENCY_PUBLIC`  
6. **GENERAL_AVAILABILITY** — `NORMAL_PRODUCTION`  

Each advance requires certification (where applicable), SLO compliance, confidence ≥ 0.75, and operator sign-off. Rollback maps to shadow + `INTERNAL_SHADOW`.

## Activation checklist

- [ ] `/config_status` — no errors  
- [ ] `/certification_status` — CERTIFIED  
- [ ] `/go_live_check` — ready  
- [ ] `RC1_LOCKDOWN_MODE=true` for production  
- [ ] `/activation_status` — review next stage  
- [ ] `/activate_next_stage` — with operator present  
- [ ] `/launch_dashboard` — monitor 24h  
- [ ] `/slo_live` + `/error_budget` — no burn  
- [ ] Chaos disabled: `OPS_CHAOS_ENABLED=false`  

## Rollback procedure

1. `/activation_rollback <reason>`  
2. Confirms shadow rollout via production safety  
3. `/freeze_editorial` if needed  
4. `RECOVERY_MODE=true` only with runbook approval  
5. Export: `/recovery_state` + config snapshot via `/config_diff`  

## Environment

```bash
RC1_ENABLED=true
RC1_LOCKDOWN_MODE=false   # true in production go-live
RC1_PROFILING=true
RC1_BASELINES=true
RC1_ACTIVATION=true
```

## Related

- `docs/OPS_CERTIFICATION.md`
- `docs/PRODUCTION_GO_LIVE_CHECKLIST.md`
- `docs/LIVE_OPS_ARCHITECTURE.md`
