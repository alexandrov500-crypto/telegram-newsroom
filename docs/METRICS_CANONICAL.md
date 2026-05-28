# Canonical metrics (frozen set)

Avoid adding metrics without updating this list.

## Histograms

- `scheduler_cycle_duration_seconds`
- `publish_duration_seconds`
- `openai_request_duration_seconds`

## Counters

- `publishes`, `publish_failures`, `publish_retries`
- `drafts_created`
- `telegram_conflict_total`, `openai_failure_total`

## Gauges

- `queue_depth`
- `openai_circuit_open`

## Derived (ops panel / logs, not Prometheus required)

- drafts/hour — from `pipeline_ticks`
- retry rate — `failed_drafts` / publishes
- stale ticks — `pipeline_ticks WHERE status='stale'`
- maintenance activations — `auto_maintenance.json`

Audit helper: `observability/canonical_metrics.py`
