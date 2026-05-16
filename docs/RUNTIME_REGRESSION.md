# Runtime regression comparison (baseline vs current)

This layer compares **two existing** `runtime_bundle.zip` artifacts (see `docs/RUNTIME_ARTIFACTS.md`). It does **not** collect metrics at runtime, does not require Redis or network, and is **not** a telemetry or anomaly-detection platform.

## Purpose

- **CI / nightly**: fail a job when the current bundle regresses vs a stored baseline (memory, queue hints, JSON state sizes, moderation latency, bounded failure counters).
- **Release qualification**: compare release candidate bundle to last known-good bundle.
- **Postmortem**: attach baseline + incident bundles and run the tool locally for a structured diff.

## Baseline workflow

1. Run a healthy pipeline (benchmark → soak → `build_runtime_artifact_bundle.py`).
2. Copy `artifacts/runtime_bundle.zip` to `runtime_baselines/stable_bundle.zip` (versioned tag or commit-stamped name).
3. For each nightly run, produce a new bundle and compare against the baseline.

## CLI

```bash
python tools/compare_runtime_baseline.py \
  --current artifacts/runtime_bundle.zip \
  --baseline runtime_baselines/stable_bundle.zip \
  --warning-threshold-pct 15 \
  --fail-threshold-pct 50 \
  --json-output artifacts/regression.json \
  --output-report artifacts/regression.txt
```

Flags:

| Flag | Meaning |
|------|---------|
| `--strict` | Exit non-zero if overall status is not `OK`, or if bundle JSON failed to parse (load warnings). |
| `--ignore-missing` | If baseline or current lacks a scalar for a metric, treat that row as OK instead of WARNING. |

Exit codes: `0` when overall is `OK` and not `--strict` with warnings; `1` when overall is `FAIL`, or under `--strict` when overall is not `OK` or there are load warnings.

## Metrics (bounded, operational)

Scalars are extracted from `stability.json` / `benchmark.json` inside the zip (see `utils/runtime_regression.METRIC_ORDER`). **Increases are treated as worse** (regression). Decreases or flat changes are `OK`.

| Area | Examples |
|------|-----------|
| Memory | `rss_mb`, `peak_rss_mb` (peak uses `runtime_summary.bounded_state_report.rss_bytes` when present) |
| Queue | `avg_oldest_pending_age_sec_sampled_kinds`, `queue_pressure_score`, `pending_jobs_total` |
| Runtime JSON sizes | `event_history_bytes`, `timeline_bytes`, `suppression_bytes`, `drift_bytes` |
| Moderation | `avg_moderation_publish_latency_sec`, `avg_publish_attempts_recent` |
| Reliability | `reconnect_count` (Telethon counter), `recovery_count` (transport recoveries when embedded), `transport_failures` (bounded sum of select failure counters) |

If a field is absent in both bundles, the row is `OK`. If only one side is missing and `--ignore-missing` is off, the row is `WARNING`.

## Interpreting WARNING vs FAIL

- **OK**: no regression vs baseline, or improvement (non-positive % change).
- **WARNING**: positive % change at or above `--warning-threshold-pct` but below `--fail-threshold-pct`.
- **FAIL**: positive % change at or above `--fail-threshold-pct`.

Overall status is the worst row status (`FAIL` > `WARNING` > `OK`).

## Example regression report

```text
Runtime regression summary

baseline: runtime_baselines/stable_bundle.zip
current:  artifacts/runtime_bundle.zip

RSS memory: +11.2% OK
queue oldest age: +44.0% WARNING
moderation latency: +67.0% FAIL
event_history size: +3.0% OK

Overall status: FAIL
```

## Nightly CI flow (example)

1. `python tools/runtime_benchmark.py --json-out …` (optional `--sample-transport` on hosts with Redis).
2. `python tools/soak_runner.py --profile low --max-ticks 200 --json-out $RUNTIME_STATE_DIR/soak_report.json`
3. `python tools/build_runtime_artifact_bundle.py --runtime-dir $RUNTIME_STATE_DIR --output artifacts/runtime_bundle.zip`
4. `python tools/compare_runtime_baseline.py --current artifacts/runtime_bundle.zip --baseline runtime_baselines/stable_bundle.zip --strict --json-output artifacts/regression.json`
5. `actions/upload-artifact` for `artifacts/runtime_bundle.zip` and `artifacts/regression.json`.

## Implementation notes

- Logic lives in `utils/runtime_regression.py`; CLI is `tools/compare_runtime_baseline.py`.
- JSON output is sorted keys for stable diffs in CI.
- Corrupt JSON members in a zip are skipped with warnings; other members may still allow a partial comparison.
