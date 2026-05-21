# Operational economics

Cost-aware, bounded autonomous operation (resource accounting, AI budgets, throughput adaptation, storage governance).

## HTTP endpoints (ops token)

| Path | Description |
|------|-------------|
| `GET /runtime/economics/resources` | Hourly/daily rollups + live counters |
| `GET /runtime/economics/budgets` | AI limits, usage, pressure, cooldown |
| `GET /runtime/economics/mode` | Economic mode profile |
| `GET /runtime/economics/throughput` | Adaptive throughput state |
| `GET /runtime/economics/storage` | Storage breakdown + pressure |
| `GET /runtime/economics/roi` | Editorial efficiency metrics |
| `GET /runtime/economics/slo` | SLO status |
| `GET /runtime/economics/load_shedding` | Active shedding measures |

`POST /ops/control/economic/mode` — set `low_cost`, `balanced`, `high_quality`, `crisis_mode`, `burst_mode`.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `AI_MAX_TOKENS_PER_HOUR` | 120000 | Hourly token cap |
| `AI_MAX_REQUESTS_PER_HOUR` | 60 | Hourly request cap |
| `AI_COOLDOWN_SEC` | 0 | Manual cooldown extension |
| `RUNTIME_ECONOMIC_MODE` | balanced | Default economic mode |
| `RUNTIME_STORAGE_QUOTA_BYTES` | 2GB | Storage pressure threshold |
| `ECONOMICS_HOURLY_BUCKETS_MAX` | 168 | Hourly rollup retention |
| `ECONOMICS_DAILY_BUCKETS_MAX` | 90 | Daily rollup retention |

## Economic modes

| Mode | AI | Retention | Snapshots |
|------|-----|-----------|-----------|
| low_cost | minimal, 50% token scale | 0.8× | 24h |
| balanced | standard | 1.0× | 12h |
| high_quality | full | 1.1× | 6h |
| crisis_mode | breaking-only bias | 0.7× | 4h |
| burst_mode | 1.5× token scale | 1.0× | 8h |

## Load shedding

Under composite pressure (queue, scheduler lag, OpenAI latency, budget):

- Low-priority summarize skip
- Reduced summarize depth
- Replay paused
- Analytics/notification throttling

Publish integrity, audit ledger, and publish journal are never disabled.

## Artifacts

Under `{RUNTIME_STATE_DIR}/economics/`:

- `resources_hourly.json`, `resources_daily.json`
- `budget_state.json`, `throughput_state.json`, `storage_state.json`
- `economic_mode.json`, `roi_daily.json`, `slo_status.json`, `load_shedding.json`

## CLI

```bash
python -m tools.simulate_load
python -m tools.simulate_load -o /path/to/scalability_report.json
```

Generates `scalability_report.json` with scenario risks (source burst, OpenAI outage, queue saturation, publish spikes, incident storm).

SLO snapshot refreshed on heartbeat → `economics/slo_status.json`.

## Logs

- `storage.pressure.warning` — storage ≥ 75% quota
- `scheduler.summarize_skipped` with `stage=ai_budget` or `load_shedding`
