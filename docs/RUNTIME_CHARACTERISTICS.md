# Runtime characteristics & operational limits

Production-lite deployment targets **single-process or small fixed worker counts**, JSON-on-disk runtime state, optional Redis for queues/locks, and SQLite or Postgres for the editorial database.

## Queues

- **Redis disabled**: in-memory reliable transport (development / tests). Depth is process-local.
- **Redis enabled**: depth per `JobKind` is exposed via `gather_runtime_health` and `tools/runtime_benchmark.py`. Tune `runtime_queue_pending_warn` / `runtime_queue_growth_warn_depth` in `Settings` when backlog routinely exceeds comfort (defaults are documented in `app/config.py` env mapping).

## Redis

- Typical footprint: small keys for job streams, publish idempotency (`{prefix}:publish_idem:*`, TTL seven days when Redis path is used), heartbeat keys with TTL aligned to `worker_heartbeat_ttl_sec`.
- **Reconnect**: `reconnect_redis(settings)` closes the singleton and re-runs `init_redis_from_settings`.

## SQLite

- WAL mode + busy timeout (see `db/session.py`). File growth correlates with raw posts + drafts + audit columns. Built-in analyze/vacuum intervals are hour-based env knobs (`sqlite_analyze_interval_hours`, `sqlite_vacuum_interval_hours`).
- `:memory:` databases (tests) do not exercise WAL file growth.

## Postgres

- Use async URL (`postgresql+asyncpg://...`). Pool sizing follows `database_pool_size` / `database_max_overflow`. Operational limits match your instance RAM and connection cap — the codebase does not auto-scale pools.

## Runtime JSON (`RUNTIME_STATE_DIR`)

| File | Growth guard |
|------|----------------|
| `operational_timeline.json` | `append_timeline_event` caps entries (default 240). `admin_cli runtime-compact-state` trims by age + cap. |
| `suppression_state.json` | TTL map capped at 200 entries; `prune_expired_suppression_entries` removes expired keys; duplicate burst object resets via emergency CLI. |
| `editorial_drift_snapshots.json` | `append_drift_snapshot` caps at 48; compaction CLI trims further. |
| `event_history.json` | `append_event_history` caps at 120 rows; `compact_event_history` + `admin_cli runtime-compact-state` trim by age/cap. |
| `topic_memory.json` | Prunes stale topics by `window_hours` and `max_topics` inside `bump_topic`. |

## Metrics & worker memory

- `utils.metrics` counters are in-process (reset via tests or explicit operator action).
- Worker retry ring (`workers/state.py`) retains at most **512** monotonic timestamps for storm detection — bounded memory.

## Soak / benchmark CLIs

- `python tools/soak_runner.py --profile medium --max-ticks 500`
- `python tools/runtime_benchmark.py --json-out /tmp/bench.json`
- Optional **queue lag sample** (briefly connects Redis + reliable transport, then closes):  
  `python tools/runtime_benchmark.py --sample-transport --json-out /tmp/bench.json`  
  Adds `transport_sample.pressure_by_kind` and copies `avg_oldest_pending_age_sec_sampled_kinds` into `derived` when present (Redis tail jobs with `_enqueue_wall_ts` only).

## Degraded modes

- **Redis down while enabled**: transport falls back depending on configuration; health shows degraded Redis; publish idempotency uses in-memory store unless Redis recovers (cross-restart dedupe prefers Redis when configured).
- **Safe mode / dry run**: publication and external side effects short-circuit per `Settings` (see `app/config.py`).

## Recommended deployment sizes (starting points)

| Profile | vCPU | RAM | Notes |
|---------|------|-----|-------|
| Lite (SQLite, no Redis) | 1 | 1–2 GiB | Dev / small pilot |
| Standard (Postgres + Redis) | 2 | 2–4 GiB | Typical single-region newsroom |
| Bursty ingest | 2–4 | 4–8 GiB | Many channels; watch queue depth + RSS trends |

These are **heuristic** — validate with soak exports and host metrics for your channel volume.
