# Post-GA Live Operations Tuning

First live public operations window — adaptive calibration, quality learning, risk prediction, and operator load reduction.

## When to enable

Set `POST_GA_ENABLED=true` in **production** after `GENERAL_AVAILABILITY` activation and stable `/ga_evaluate` (GA_READY).

## Operator commands

| Command | Purpose |
|---------|---------|
| `/traffic_calibration` | Pacing factor + efficiency |
| `/audience_health` | Responsiveness score |
| `/quality_trends` | Confidence + drift forecast |
| `/source_quality` | Weak source rankings |
| `/operator_load` | Ranked alert queue |
| `/attention_risk` | Operator fatigue risk |
| `/risk_forecast` | 6h predictive risks |
| `/future_pressure` | Top pressure + confidence |
| `/governance_trends` | Trust trajectory |
| `/trust_evolution` | Trust range + trend |
| `/live_exec` | Executive live dashboard |
| `/optimization_pending` | Self-optimization proposals |

HTTP: `GET /post_ga`

## Safe self-optimization

- Proposals stored in `ops_post_ga_optimization`
- Impact above `POST_GA_OPT_THRESHOLD` (default 5%)
- Operator approval required before apply
- Full audit trail on apply

## Daily operations rhythm

1. `/live_exec` — morning executive check  
2. `/traffic_calibration` + `/audience_health`  
3. `/risk_forecast` — before peak hours  
4. `/operator_load` — shift handoff  
5. `/quality_trends` — end of day  
6. Review `/optimization_pending` weekly  

## Integration

- Quality learning hooks in `publish_pending_item()` after GA quality pass
- Calibration + analytics recorded on successful publish
- Ops tick merges signals from GA/RC1 layers

## Related

- `docs/GA_OPERATIONS.md`
- `docs/RC1_ACTIVATION.md`
