# GA Operations Package

Pre–General Availability execution layer: traffic guardrails, AI quality, feedback, retention, scaling, rollback safety, and GA readiness.

## Operator commands

| Command | Purpose |
|---------|---------|
| `/traffic_guardrails` | Pressure level + freeze state |
| `/publish_load` | Rate + scaling risk |
| `/quality_live` | Rolling quality average |
| `/quality_trace <story_id>` | Per-story quality scores |
| `/ops_advisor` | Automated hints + checklist |
| `/maintenance_status` | Maintenance window (04:00 UTC) |
| `/ga_status` | Current GA readiness state |
| `/ga_evaluate` | Re-run GA readiness checks |
| `/production_summary` | Executive production dashboard |

HTTP: `GET /ga`

## Traffic pressure levels

- `PUBLIC_TRAFFIC_SAFE` — normal pacing
- `TRAFFIC_PRESSURE_HIGH` — elevated queue or rate
- `TRAFFIC_PRESSURE_CRITICAL` — block new publishes

Integrated into `publish_pending_item()` after reliability gate.

## GA readiness states

| State | Meaning |
|-------|---------|
| `PRE_GA` | Blockers present |
| `GA_CANDIDATE` | Partial readiness |
| `GA_READY` | Eligible for general availability |
| `GA_LOCKED` | Manual lock |

## GA activation checklist

1. `/config_status` — no errors  
2. `/certification_status` — CERTIFIED  
3. `/ga_evaluate` — GA_READY  
4. `/launch_dashboard` + `/production_summary`  
5. `/activation_status` — advance to GENERAL_AVAILABILITY  
6. `OPS_CHAOS_ENABLED=false`  
7. Monitor `/traffic_guardrails` and `/publish_load` for 48h  

## Rollback guarantees

- Snapshots via `RollbackSafetyManager` — integrity hash, no republish flag  
- `/activation_rollback` preserves audit chain (RC1 + ops cert)  
- Dry-run available before staged rollback  

## Environment

```bash
GA_OPS_ENABLED=true
GA_TRAFFIC_GUARDRAILS=true
GA_QUALITY_VALIDATION=true
GA_MAX_PUBLISHES_PER_HOUR=40
GA_READINESS_MIN_SCORE=0.88
```

## Related

- `docs/RC1_ACTIVATION.md`
- `docs/OPS_CERTIFICATION.md`
- `docs/PRODUCTION_GO_LIVE_CHECKLIST.md`
