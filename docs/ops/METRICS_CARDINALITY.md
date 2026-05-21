# Metrics cardinality policy (newsroom runtime)

Production Prometheus export uses **in-process counters, gauges, and histograms** without dynamic label dimensions. Metric names are prefixed `newsroom_` at scrape time.

## Safe pattern (current)

| Type | Names | Labels |
|------|-------|--------|
| Counter | `posts_collected`, `openai_failures_total`, `queue_overflow_total`, … | **None** |
| Gauge | `queue_depth`, `openai_circuit_open`, `average_quality_score`, … | **None** |
| Histogram | `collect_duration_seconds`, `scheduler_cycle_duration_seconds`, `recovery_duration_seconds`, … | **Fixed buckets only** |

**Rule:** Never add `channel`, `draft_id`, `post_id`, `bot_username`, or free-text `reason` as Prometheus labels.

## Forbidden (would explode cardinality)

- Per-source-channel counters
- Per-draft or per-cluster histograms
- Error message strings as labels
- `runtime_id` / `git_sha` as metric labels (use logs or `/runtime/status` instead)

## Runtime dimensions (not in Prometheus)

Use HTTP JSON instead:

- `GET /runtime/status` — `runtime_id`, `git_sha`, uptime
- `GET /health` — `runtime` block
- Structured logs — `runtime_id`, `git_sha`, `correlation_id`, `tick_id`

## Histogram catalog

| Metric | Unit | Purpose |
|--------|------|---------|
| `collect_duration_seconds` | s | Telethon collect phase |
| `summarize_duration_seconds` | s | OpenAI cluster summarize |
| `scoring_duration_seconds` | s | Editorial intelligence enrich |
| `publish_duration_seconds` | s | Scheduled publish phase |
| `scheduler_cycle_duration_seconds` | s | Full pipeline tick wall time |
| `recovery_duration_seconds` | s | OpenAI circuit open → closed |
| `degradation_duration_seconds` | s | Time spent degraded (circuit) |

## Review checklist (before adding metrics)

1. Is the name static (not formatted with user data)?
2. Are labels absent or from a fixed enum ≤ 10 values?
3. Could this metric grow with channel count or draft volume? → use logs/timeline instead.
4. Document new metrics in this file and `docs/ops/OBSERVABILITY_OPS.md`.

## Bot stack (separate process)

`bot/observability/metrics.py` uses `prometheus_client` with labels in the **bot** process only. Do not merge bot histograms into newsroom `/metrics` without a cardinality audit.
