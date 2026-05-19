# Production SLO handbook

## Service objectives

| SLO | Target | Measurement |
|-----|--------|-------------|
| Epistemic stability | ≥ 0.75 | `epistemic_stability` burn-in samples |
| Mesh health | ≥ 0.70 | Federated mesh resilience gauge |
| Queue backlog | < 500 sustained | Prometheus `newsroom_queue_backlog` |
| Replay divergence | < 0.10 | `ReplaySustainability.measure_replay_health` |
| Daily cost | < budget | `ops_daily_cost_reports` |
| Operator alert fatigue | < 20 open | `/dashboard` open count |

## Error budgets

- Burn-in health mean must stay above 0.80 over 7d window
- Max 3 epistemic regression alerts per day (deduplicated)
- Certification must pass nightly

## Staging → production gate

`ProductionReadinessExecution.PROMOTION_THRESHOLD` = **0.75**

Score = 0.4×health + 0.35×epistemic + 0.25×(1 − backlog_penalty), only if certification passes.

## Observability

- Grafana: `deploy/grafana/dashboards/staging-readiness.json`
- Explorers: `/ops/explorer/*`
- Traces: Tempo/Jaeger via `deploy/staging/tempo.yaml`

## Review cadence

- Daily: cost report tick
- Weekly: burn-in markdown report
- Monthly: storage growth + replay compaction review
