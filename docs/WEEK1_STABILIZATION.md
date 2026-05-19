# Week-1 Production Stabilization

First week of **real public operation** — alert noise reduction, quality tuning, operator copilot, baselines, survivability.

## Enable

```bash
WEEK1_STABILIZATION_ENABLED=true
WEEK1_ALERT_DEDUPE_SEC=900
WEEK1_ACTIONABLE_ONLY=true
```

Activates with `LIVE_DEPLOY_ENABLED` when unset.

## Telegram commands

| Command | Purpose |
|---------|---------|
| `/alert_quality` | Surfaced vs suppressed alerts, root-cause tags |
| `/noise_index` | Alert fatigue metric |
| `/quality_adaptation` | Live quality recommendations |
| `/audience_fatigue` | Publish fatigue score |
| `/ops_copilot` | Grounded risk summary + next actions |
| `/what_changed_24h` | Drift vs frozen baselines |
| `/stabilization_risk` | Short-term stabilization score |
| `/rollback_probability` | Estimated rollback likelihood |
| `/week1_report` | Executive week-1 summary |
| `/launch_confidence` | Launch confidence index |
| `/adaptive_recommendations` | Safe tuning proposals (approval required) |
| `/optimization_safety` | Proposal safety review |
| `/survivability` | Real-operation survivability score |
| `/confidence_trend` | Operational confidence trend |
| `/week1_baselines` | Canonical healthy-state capture status |

## Alert noise reduction

Integrated into `AlertManager` — duplicate and non-actionable alerts suppressed before Telegram delivery. Logs in `week1_alert_log`.

## Baselines

After ~12 stable ops ticks (low risk, queue &lt; 120), captures baselines for:

`runtime`, `traffic`, `quality`, `queue`, `cognition`, `operator_load`

Used by `/what_changed_24h` and future drift detection.

## Daily operator rhythm

1. `/take_shift` → `/ops_copilot`
2. `/stabilization_risk` + `/survivability`
3. `/noise_index` if alert volume feels high
4. `/adaptive_recommendations` — approve only low blast-radius items
5. `/week1_report` before end of shift

## HTTP

`GET /week1` — tick snapshot + baseline status

## Related

- `docs/FIRST_72H_LIVE_OPERATIONS.md`
- `docs/OPS_PLAYBOOK.md`
