# Publishing intelligence (cadence, gates, priority)

Lightweight pacing and **explainable** scores layered on top of the existing publish path (no Celery/Kafka).

## Cadence (`editorial/cadence.py`)

- `record_publish(runtime_dir, topic_key=…)` — updates `publish_cadence.json` (`last_publish_unix`, rolling `recent` rows).
- `cadence_should_defer_cluster` — may **defer** summarization for this tick (posts stay unprocessed): repeated topic in recent window, short gap after last publish, quiet hours (non-urgent).
- `evaluate_publish_gate` — blocks **approve/send** when quiet hours, min interval, or burst cap would be exceeded (breaking stories bypass quiet hours).
- `topic_dedupe_key` — stable short key from topic hint for cadence bookkeeping.

## Publication scores (`editorial/publication_priority.py`)

- `compute_publication_priority_score` — merges breaking block, evolution kind, duplicate %, editorial priority dict.
- `compute_publish_readiness_score` — combines confidence, headline quality heuristic, source diversity ratio, cadence gate preview.

Scheduler merges `publication_intel` into `draft_extras` after tags/breaking.

## Publish integration (`publisher/publish_service.py`)

Before `approve_draft`, the service evaluates `evaluate_publish_gate`. On block it returns `PublishFlowOutcome.CADENCE_DEFERRED` (draft stays pending). On success it calls `record_publish` after DB finalize.

## Suppression memory (`editorial/suppression_memory.py`)

- TTL map in `suppression_state.json` (`record_suppression_ttl`, `is_suppression_active`).
- `bump_duplicate_burst` / `duplicate_burst_count` — duplicate-storm signal (scheduler increments on duplicate skip).

## Pipeline decision (`editorial/pipeline_decision.py`)

`evaluate_unified_cluster_stage` composes policy relevance, adaptation thresholds, cadence defer, TTL suppression, burst storm, and topic memory saturation/cooldown. Output is serialized under `draft_extras.cluster_intelligence.pipeline_decision.editorial_pipeline`.

## Drift snapshots (`editorial/drift_detection.py`)

`evaluate_editorial_drift` compares the latest stored snapshot to current metrics (acceptance, suppression rate, confidence). `append_snapshot=False` avoids writes (CLI `--no-append`).

## CLI

```bash
python3 -m tools.admin_cli cadence-report --json
python3 -m tools.admin_cli suppression-report --json
python3 -m tools.admin_cli topic-saturation-report
python3 -m tools.admin_cli editorial-drift-report --no-append --json
python3 -m tools.admin_cli pipeline-decision-inspect --json
```

## Metrics

- `cadence_deferred_cluster` — summarization tick deferred by cadence.
- `cadence_blocked_publish` — publish gate blocked approve path.
