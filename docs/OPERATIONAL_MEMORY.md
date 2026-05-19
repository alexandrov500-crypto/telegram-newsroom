# Operational Memory + Predictive Stability Layer

Production evolution layer after Week-1 stabilization. The system learns how operations behave under real traffic and surfaces explainable instability risk before operators notice degradation.

## Goals

- Append-only incident memory with fingerprints and recurrence tracking
- Explainable predictive risk (15m / 1h / 6h / 24h) without ML infrastructure
- Drift monitoring (transient vs systemic)
- Time-aware seasonality baselines
- Advisory recommendations grounded in history
- Operator commands and HTTP snapshots — telemetry only, no hallucinations

## Package layout

```
bot/operational_memory/
  memory_store/incidents.py   # incident capture
  fingerprints/engine.py      # pattern hashing
  prediction/engine.py        # horizon risk
  drift/monitor.py            # domain drift
  seasonality/calendar.py     # weekday/hour buckets
  recommendations/v2.py       # advisory proposals
  learning/outcomes.py        # recovery patterns
  repository.py               # SQLite persistence
  coordinator.py              # tick orchestration
  factory.py / context_holder.py
  command_center/handlers.py  # Telegram commands
```

## Enable

```bash
OPERATIONAL_MEMORY_ENABLED=true   # or WEEK1_STABILIZATION_ENABLED=true
OPMEM_RETENTION_DAYS=90
```

Runs on operator nodes only (`role_allows_operator`). Wired into the ops scheduler tick after Week-1 enrichment (`stabilization_risk`, `survivability_score`, etc.).

## Operator commands

| Command | Purpose |
|---------|---------|
| `/incident_history` | Recent incidents from memory |
| `/recurrent_failures` | Types with ≥2 occurrences |
| `/predictive_risk` | Horizon risk table |
| `/drift_report` | Latest drift by domain |
| `/seasonality_state` | Current time bucket baseline |
| `/incident_fingerprint` | Top recurring fingerprint |
| `/recovery_patterns` | Historical recovery durations |
| `/operational_memory` | Layer summary |
| `/preventive_actions` | Pending advisory proposals |
| `/risk_forecast` | 24h forecast summary |

All outputs are grounded in SQLite telemetry — no LLM generation.

## HTTP API

- `GET /operational_memory` — tick + snapshot
- `GET /predictive_risk` — latest horizon predictions
- `GET /incident_patterns` — recurrent types + fingerprints
- `GET /drift_state` — per-domain drift
- `GET /seasonality` — active bucket profile

## Storage

Tables: `opmem_incidents`, `opmem_fingerprints`, `opmem_predictions`, `opmem_drift_snapshots`, `opmem_seasonality_profiles`, `opmem_recommendations`, `opmem_state`.

Retention: periodic prune of incidents older than `OPMEM_RETENTION_DAYS` (append-only until prune).

## Safety model

- **Advisory only** — recommendations require operator approval (`approved=0` until acknowledged)
- **No autonomous destructive actions** — no auto-tuning, no auto-rollback
- **Explainable predictions** — each horizon stores `explain_json` (base risk, slopes, recurrent boost)
- **Low noise** — incident auto-capture uses thresholds (`OPMEM_QUEUE_SPIKE`, `OPMEM_RETRY_STORM`)

## Rollout strategy

1. Deploy schema (automatic via `init_database`)
2. Enable on operator node with `OPERATIONAL_MEMORY_ENABLED=true`
3. Run 24–48h in observe-only mode (default) — verify `/incident_history` and HTTP endpoints
4. Tune thresholds from baselines (`OPMEM_QUEUE_SPIKE`)
5. Integrate preventive actions into ops playbook approval flow (manual)

## Failure modes

| Failure | Mitigation |
|---------|------------|
| SQLite write pressure | Append-only + periodic prune; batch writes per tick |
| False incident spikes | Raise `OPMEM_QUEUE_SPIKE`; seasonality adjusts baselines |
| Stale predictions | Requires continuous ops ticks; HTTP shows last stored horizon |
| Double tick | Single opmem tick per ops cycle after Week-1 enrichment |
| Layer offline | Commands return "Operational memory layer offline" |

## Tests

```bash
pytest tests/test_operational_memory.py -q
```
