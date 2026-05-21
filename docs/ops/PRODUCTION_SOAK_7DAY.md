# Production soak — first 7 days (operational hardening)

Baseline after Phase 2.1 + runtime hardening. Use this checklist while OpenAI remains region-degraded.

## Daily checks (5 min)

1. `curl -s http://127.0.0.1:8080/health | jq '.status, .runtime'`
2. `docker inspect --format='{{.State.Health.Status}} restarts={{.RestartCount}}' telegram-newsroom`
3. `curl -s http://127.0.0.1:8080/metrics | grep -E 'openai_circuit|queue_depth|collect_duration|scheduler_cycle'`
4. `docker logs --since 24h telegram-newsroom 2>&1 | grep -E 'runtime\.(boot|ready|degraded|recovered)|watchdog\.|openai\.circuit' | tail -30`

## Success signals

| Signal | Expectation |
|--------|-------------|
| `RestartCount` | Stable at 0 across days |
| `/health` status | `degraded` OK when OpenAI blocked; not `unhealthy` unless DB down |
| `runtime.uptime_sec` | Monotonic growth, no frequent `runtime.boot` |
| `openai_circuit_state` | `open` during outage; transitions to `half_open` / `closed` after recovery window |
| `queue_overflow_total` | Near zero; spikes → investigate worker enqueue pressure |
| Histogram `_count` | Grows with pipeline ticks (`scheduler_cycle_duration_seconds`) |

## Structured log examples

```text
runtime.boot | {"runtime_id":"…","git_sha":"…","build_version":"3.0.0","uptime_sec":0.001}
runtime.ready | {"ai_pipeline_enabled":false,"collector_enabled":true,"aggregate_status":"degraded"}
scheduler.tick.started | {"tick_id":"tick-1-…","uptime_sec":12.4}
scheduler.tick.completed | {"wall_sec":36.8,"event_duration_ms":36800}
collector.batch.completed | {"new_rows":104,"event_duration_ms":1200}
runtime.degraded | {"reason":"openai_circuit_open","openai_circuit_state":"open"}
openai.circuit.open | {"consecutive_failures":5,"recovery":"OPENAI_DISABLED"}
```

## Prometheus examples

```text
newsroom_openai_failures_total 12
newsroom_openai_circuit_open 1
newsroom_openai_recovery_attempts_total 2
newsroom_queue_depth 0
newsroom_collect_duration_seconds_count 96
newsroom_scheduler_cycle_duration_seconds_sum 1842.5
```

## Watchdog warnings (non-fatal)

- `watchdog.scheduler.stalled` — no tick longer than ~2.5× pipeline interval
- `watchdog.collector.stalled` — collector enabled but no successful collect
- `watchdog.exception_burst` — many `pipeline_inner_failed` in 5 minutes
- `watchdog.event_loop.lag` — asyncio scheduling delay above threshold

## OpenAI recovery procedure

1. Fix region/proxy so `openai.models.retrieve` succeeds from VPS.
2. Restart container **or** wait for circuit half-open probe + successful summarize.
3. Confirm logs: `openai.circuit.closed`, `runtime.recovered`, `ai_pipeline_enabled=true` on `/health`.
4. Verify `editorial.scoring.completed` after first draft tick.

## Incident bundle

```bash
bash /opt/newsroom/tools/debug_telegram_runtime.sh /tmp/newsroom-soak-$(date -u +%Y%m%d).tar.gz
```

## Env knobs (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_CIRCUIT_FAILURE_THRESHOLD` | 5 | Failures before OPEN |
| `OPENAI_CIRCUIT_OPEN_SEC` | 300 | Open duration |
| `OPENAI_CIRCUIT_RECOVERY_PROBE_SEC` | 60 | Half-open probe interval |
| `JOB_QUEUE_MAX_SIZE` | 500 | Per-kind bounded queue |
| `WATCHDOG_SCHEDULER_STALL_MULTIPLIER` | 2.5 | Stall detection |
| `WATCHDOG_EXCEPTION_BURST_COUNT` | 10 | Burst threshold |

## Migration notes

- **No Alembic migration** — operational layer only.
- Deploy: `git pull` + `docker compose build` + `up -d` on VPS.
- Existing `runtime_ops` / notification rate limits unchanged.
