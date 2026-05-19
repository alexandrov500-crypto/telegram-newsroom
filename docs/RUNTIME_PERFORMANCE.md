# Runtime performance — asyncio event loop safety

Pilot and production operator nodes run a single asyncio event loop. Any **blocking call on that loop** delays Telegram polling, health probes, controlled-live ticks, and operator commands.

## Lag detection

`BurnInWatchdog` measures scheduling lag every `WATCHDOG_INTERVAL_SEC` (default 30s). When lag exceeds `2.0s`, a **critical** alert fires and structured context is logged:

- `lag_sec`, `lag_avg_sec`, `lag_max_sec`
- `active_tasks` — running asyncio task names
- `current_job` / `db_operation` — from `bot.observability.loop_diagnostics`
- `publishing_active`, `telegram_request_active`, `openai_request_active`
- `slow_job_count`, `slow_db_operation_count`

HTTP: `GET /runtime_performance`  
Telegram: `/live_dashboard`, `/channel_health` include loop lag summary.

Prometheus-style gauges (when metrics enabled):

- `event_loop_lag_avg_seconds`
- `event_loop_lag_max_seconds`
- `slow_job_total{job_name}`
- `slow_db_operation_total{operation}`

## Forbidden blocking patterns

Do **not** on the main event loop:

- `time.sleep()` — use `await asyncio.sleep()`
- `requests.get/post` — use `aiohttp` or `asyncio.to_thread()`
- `feedparser.parse()` / RSS fetch — use `asyncio.to_thread(fetch_feed_items, url)` (ingestion already does)
- `validate_catalog()` synchronously for many feeds — use `validate_catalog_async()`
- Long synchronous SQLite batches — use `track_sync_db()` + keep transactions short, or `asyncio.to_thread()`
- `subprocess.run()` without executor
- Large synchronous JSON/file writes in handlers

## Async DB rules

- SQLite repositories are sync by design; treat each `connect()` + query as a **blocking section**.
- Wrap hot paths with `track_sync_db("operation_name")` for visibility.
- Avoid holding a connection open across `await` points.
- Never run full-table compaction or multi-feed validation inside a Telegram handler.

Heavy maintenance runs in `operations_platform.operational_tick` via:

- `await feed_validation.validate_catalog_async()` (thread pool per feed)
- `await asyncio.to_thread(storage.run_maintenance)` (compaction)

**Startup:** tick `0` no longer runs feed validation, storage compaction, epistemic snapshot, or replay indexes (see `main.py` operations loop). This prevents multi-second blocking right after pilot activate.

## Scheduler / background loop safety

- Register loops in `LoopHeartbeatRegistry` via `heartbeat(name, duration_sec)`.
- Wrap heavy ticks with `async timed_async_job("job-name")`:
  - **≥ 1.0s** → warning log `event=slow_job`
  - **≥ 3.0s** → critical slow job counter
- APScheduler diagnostics: `utils.scheduler_diagnostics.record_scheduler_run()`

## OpenAI timeout policy

- Use async OpenAI client paths only from async code.
- Set explicit timeouts on API calls (project defaults in enrichment pipeline).
- Record in-flight state with `openai_request_active()` when adding new call sites.
- On sustained failures, production safety circuit breakers apply — do not disable breakers to “fix” lag.

## Logging recommendations

- Prefer structured `event=` logs over huge payload dumps in tight loops.
- On lag critical, inspect `event=event_loop_lag_detected` context before scaling publish rate.
- Check `recent_slow_jobs` in `/runtime_performance` after spikes.

## Pilot policy until lag is stable

```bash
LIVE_MODE=canary
LIVE_CANARY_MAX_PER_HOUR=3
```

Do not increase throughput until:

- `event_loop_lag_max_seconds` stays low between watchdog probes
- No repeated critical lag alerts
- `slow_job_total` not climbing on `operations-platform-tick` or `feed_validation_catalog`

## Background loop stabilization (pilot)

### RSS ingestion (`rss-ingestion`)

- Feeds fetched with `asyncio.to_thread` + **per-feed timeout** (`RSS_FEED_TIMEOUT_SEC`, default 20s).
- **Concurrency limit** (`RSS_FEED_CONCURRENCY`, default 2).
- Mid-cycle **heartbeats** every `RSS_ITEM_YIELD_EVERY` items so long cycles do not appear stalled.
- Structured log: `event=rss_ingestion_iteration` with `iteration_duration`, `network_duration`, `db_write_duration`, `longest_feed_fetch`.

### Autonomous runtime (`autonomous-runtime`)

In **canary / pilot** (`LIVE_MODE=canary` or `APP_ENV=pilot`), the loop runs in **passive mode**:

- No `recover_orphans` / `recover_stalled` / operational apply
- Tick interval **120s** (`AUTONOMOUS_PASSIVE_INTERVAL_SEC`)
- Stall threshold **120s** (not 45s)

Disable passive: `PILOT_AUTONOMOUS_PASSIVE=false`.

### Recovery cooldown

Watchdog recovery hooks are limited to **one per subsystem per 60s** (`RUNTIME_RECOVERY_COOLDOWN_SEC`). Suppressed recoveries increment `recovery_suppressed_count` instead of churning alerts.

### Soft-degraded mode

When `event_loop_lag_max ≥ SOFT_DEGRADE_LAG_SEC` (2.0) or repeated stalled loops:

- Pause ingestion
- Force autonomous passive
- Increase ingestion sleep multiplier

Clears when lag drops below `SOFT_DEGRADE_RECOVER_LAG_SEC` (0.75s) and no stalled loops.

Operator Telegram commands remain available.

### Loop health metrics

`/runtime_performance`, `/live_dashboard`, `/channel_health`:

- `rss_loop_duration_avg` / `max`
- `autonomous_loop_duration_avg` / `max`
- `stalled_loop_count`, `recovery_rate`, `autonomous_passive`

## Common root causes (observed)

1. **Synchronous RSS catalog validation** on operations tick 0 — fixed with async validation + deferred tick 0.
2. **Storage compaction** on same tick — moved to thread pool.
3. **Many feeds fetched serially** — each feed now `asyncio.to_thread` in `validate_catalog_async`.
4. **Oversized operations tick** — entire tick wrapped in `timed_async_job` for duration metrics.
