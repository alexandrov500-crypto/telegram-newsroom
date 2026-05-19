# Autonomous Operations Evolution

Long-term evolution layer for continuously operating public newsroom infrastructure.

## Enable

```bash
OPS_EVOLUTION_ENABLED=true
```

Defaults on when `POST_GA_ENABLED=true`. Staging: set explicitly in `.env`.

## Capabilities

| Area | Commands |
|------|----------|
| Operational memory | `/ops_memory`, `/incident_patterns`, `/recovery_history` |
| Strategic optimization | `/strategic_optimizations`, `/optimization_impact` |
| Cognition governance | `/narrative_health`, `/editorial_diversity` |
| Operator assistant | `/ops_assistant <q>`, `/why_alert <id>` |
| Maintenance | `/maintenance_plan`, `/maintenance_risk` |
| Maturity model | `/maturity_status`, `/maturity_trends` |
| Executive | `/evolution_report` |

HTTP: `GET /evolution`

## Principles

- **No autonomous execution** of strategic changes — proposals only
- **Grounded assistant** — cites internal memory/telemetry, no invented ops data
- **Memory aging** — archives after 90 days; recurring pattern detection
- **Evolution safety** — flags over-automation, operator disengagement, trust inflation

## Weekly operator rhythm

1. `/evolution_report` — strategic health  
2. `/maturity_status` — weakest domain  
3. `/strategic_optimizations` — review queue  
4. `/incident_patterns` — recurring issues  
5. `/maintenance_plan` — approve low-risk window tasks  

## Stack position

```
Production Safety → Reliability → Live Ops → Ops Cert → RC1 → GA Ops → Post-GA → Ops Evolution
```

## Related

- `docs/POST_GA_OPERATIONS.md`
- `docs/GA_OPERATIONS.md`
