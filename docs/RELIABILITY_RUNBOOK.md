# Production reliability & observability runbook

## Architecture

The `bot/reliability/` package composes existing ops infrastructure:

| Component | Role |
|-----------|------|
| `RuntimeHealthManager` | Subsystem heartbeats, health score, HEALTHY/DEGRADED/CRITICAL/FAILED |
| `SubsystemWatchdog` | Stall detection, bounded recovery with exponential backoff |
| `ProductionIncidentManager` | DB incidents + Telegram escalation |
| `PublishGateController` | DRY_RUN → SHADOW → LIMITED → FULL production |
| `ReliabilityCoordinator` | Single tick wired from `operations-platform` loop |
| `MetricsAggregator` | Daily report + `/costs_live` |

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RELIABILITY_LAYER_ENABLED` | `true` | Master switch |
| `RELIABILITY_BURNIN_MODE` | `false` | Verbose burn-in diagnostics |
| `RELIABILITY_PUBLISH_MODE` | (derived) | `DRY_RUN`, `SHADOW`, `LIMITED_PRODUCTION`, `FULL_PRODUCTION` |
| `RELIABILITY_PROBE_INTERVAL_SEC` | `30` | Fast health probe loop |
| `PUBLISH_STABILITY_SEC` | `3600` | Stable runtime before limited/full publish |
| `PUBLISH_MAX_QUEUE_DEPTH` | `400` | Queue gate |
| `LIMITED_PRODUCTION_CAP_PER_HOUR` | `12` | Rate cap in limited mode |
| `RELIABILITY_RECOVERY_MAX_ATTEMPTS` | `5` | Per-subsystem recovery cap |

## Operator commands

- `/health_live` — overall state, subsystem ages, publish mode
- `/queues_live` — backlog + publish gate verdict
- `/incidents_live` — open DB incidents
- `/costs_live` — token spend estimate, publish success
- `/recovery_live` — recent recovery attempts

Existing: `/runtime_live`, `/topology_live`, `/mesh_live`, `/ops_score`, `/incidents`

## Incident escalation

| Severity | Telegram | Runtime |
|----------|----------|---------|
| INFO/WARN | Log only | — |
| ERROR | Operator chat message | — |
| CRITICAL | Operator alert | — |
| FATAL | Pinned alert | `ingestion_paused=true` |

## Enabling real publishing

1. Run burn-in with `RELIABILITY_BURNIN_MODE=true` for 24h+
2. Confirm `runtime_health_score` ≥ 0.8 and no open FATAL incidents
3. Set `RELIABILITY_PUBLISH_MODE=LIMITED_PRODUCTION` (requires operator approval per publish)
4. After stability window + clean metrics → `FULL_PRODUCTION`

Keep `SHADOW_PUBLISH_ONLY=true` until sign-off.

## Reliability checklist

- [ ] `runtime_health_score` Prometheus gauge updating
- [ ] `/health_live` shows HEALTHY on operator node
- [ ] No stalled loops in `/recovery_live`
- [ ] Publish gate shows expected mode
- [ ] Daily digest received in operator chat
- [ ] Incidents auto-close after resolve workflow

## Example `/health_live` output

```
🟢 Health live
State: HEALTHY · score 0.91
Uptime: 12.3h · queue 42
Mode: SHADOW
✓ ingest: HEALTHY (45s)
✓ cognition: HEALTHY (12s)
...
```
