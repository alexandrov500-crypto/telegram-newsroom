# Soak testing (operational simulation)

This project uses **lightweight in-process soak tooling** (no Locust, k6, or Kubernetes). The goal is long-running operational validation: bounded JSON state, metrics drift, and synthetic editorial pressure without new subsystems.

## Tooling

| Path | Role |
|------|------|
| `utils/soak_simulation.py` | Async simulation core: profiles, tick loop, bounded-state report |
| `tools/soak_runner.py` | CLI: `--profile`, `--duration-sec`, `--max-ticks`, `--json-out`, `--html-out` |

## Profiles

- **low** — minimal posts/clusters + short AI latency gauge.
- **medium** — higher posts/drafts + `event_history.json` rows + multi timeline rows per tick.
- **burst** — spikes posts/clusters, synthetic queue depth, publish retries, and drift snapshot rows (capped in-file).
- **noisy_duplicate_storm** — duplicate skips, suppression TTL rows, duplicate-burst counter, publish pipeline duration samples, and moderation publish latency ring updates (bounded deque; cleared when soak resets metrics).

## CI vs production

- CI uses **`--max-ticks`** (or `max_ticks=` in tests) so runs stay deterministic and sub-second.
- Production or staging soak uses **`--duration-sec`** with a small `--tick-interval-sec` (for example 0.05–0.2s) and captures **`--json-out` / `--html-out`** via `utils/evidence_reports.build_soak_report`.

## What is measured

Each tick snapshots: Prometheus-style counters/gauges (via `utils.metrics.export_snapshot`), RSS (`utils.diagnostics.rss_bytes_best_effort`), operational timeline length and file size, suppression entry count, duplicate-burst counter, **event_history** and **drift snapshot** counts, and a **synthetic pending depth** (observability only; not the Redis queue).

## Bounded-state expectations

After a run, `collect_bounded_state_report` merges `utils.runtime_integrity` validators (timeline, suppression, **event_history** strict JSON) plus soft caps (timeline event count, large JSON warnings). Failures surface as `integrity_issues` and `ok: false` in JSON exports.

## Related

- `docs/RUNTIME_CHARACTERISTICS.md` — limits and growth expectations.
- `tools/runtime_benchmark.py` — point-in-time operational benchmark snapshot.
