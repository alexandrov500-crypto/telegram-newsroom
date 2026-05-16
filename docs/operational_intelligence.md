# Operational intelligence (v1.9)

Operator-driven predictive maintenance **without** autonomous orchestration, ML platforms, or mandatory telemetry backends.

## Predictive Maintenance Philosophy

- Intelligence is **advisory**: hints, forecasts, scores — not automated remediation.
- Deterministic heuristics over historical snapshots operators choose to retain.
- Reduce cognitive load; do not replace operator judgment.
- Complements v1.8 scalability boundaries and v1.3 drift monitoring.

## Advisory vs Mandatory Actions

| Type | Examples | Enforcement |
|------|----------|-------------|
| Advisory | WAL checkpoint hint, prune suggestion | None in tools |
| Operator-run | `make runtime-nightly`, retention CLI | Manual |
| Mandatory (release) | `make release-check` | CI / governance only |

Tools **never** mutate queues, DB, Redis, or evidence by default.

## Risk Scoring Rules

- Scores 0–100 per risk domain in `drift_forecast.py` (low / medium / high bands).
- Health score 0–100 in `operational_health.py` → `HEALTHY` | `DEGRADED` | `WARNING` | `HIGH_RISK`.
- Retry storm probability uses `retry_burst / RUNTIME_RETRY_STORM_COUNT` — explainable ratio.
- No black-box models.

## Forecast Confidence Limits

| Samples | Confidence |
|---------|------------|
| 0–2 | low |
| 3–7 | medium |
| 8+ | high |

Trends require `var/ops_history/*.json` (operator-saved `TrendSample` exports). Single-point forecasts are weak — documented in tool output.

## Unsupported Prediction Claims

- Not SLA or uptime guarantees
- Not autoscaling recommendations for K8s
- Not ML anomaly detection
- Not autonomous self-healing
- Not cross-region latency prediction

## Operator Responsibility Boundaries

Operators must:

- Validate hints against live incidents
- Quiesce systems before destructive maintenance
- Maintain history samples if trend analysis is desired
- Escalate per [scalability/scaling_governance.md](scalability/scaling_governance.md) when scores stay HIGH_RISK

## Tools (read-only)

| Tool | Purpose |
|------|---------|
| `tools/maintenance_forecast.py` | WAL, prune, snapshot cadence, retry risk |
| `tools/drift_forecast.py` | Pressure risk scores |
| `tools/maintenance_recommendations.py` | Daily/weekly/monthly/release lists |
| `tools/ops_summary.py` | CLI operational dashboard |

```bash
python3 tools/ops_summary.py
python3 tools/maintenance_forecast.py --output-dir "$OUTPUT_DIR"
```

Optional history: export JSON samples to `var/ops_history/` (manual; not automated).

## Validation

`make intelligence-validate`
