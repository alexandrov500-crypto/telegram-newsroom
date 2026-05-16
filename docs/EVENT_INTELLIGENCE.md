# Event & topic intelligence (production-lite)

This layer adds **deterministic, explainable** signals for “what is this cluster about” and “is it new or an update” — without embeddings, vector stores, or multi-agent orchestration.

## Modules

| Area | Path | Role |
|------|------|------|
| Models | `editorial/event_models.py` | `EventIdentity`, `EventCluster`, `EventEvolution` (serializable dicts) |
| Fingerprints & history | `editorial/events.py` | `compute_event_fingerprint`, rolling `event_history.json`, `classify_event_evolution` (update vs new heuristics), `event_freshness_decay` |
| Topic memory | `editorial/topic_memory.py` | Short-term counts per hashed topic hint, saturation & cooldown, JSON under `RUNTIME_STATE_DIR/topic_memory.json` |
| Entities | `editorial/entities.py` | Regex/rule extraction, normalization, co-occurrence counters in `entity_stats.json` |
| Store | `editorial/intelligence_store.py` | Atomic-ish JSON load/save helpers |

## Event fingerprint

The fingerprint is a **SHA-256** over a stable JSON encoding of per-post tuples `(id, normalized_channel, short text hash)`. Reordering posts in the cluster does not change the fingerprint because posts are sorted by id first.

## Update vs new (`EventEvolution`)

`classify_event_evolution` compares the current combined text to recent `event_history` rows:

- Exact fingerprint match → `update`, continuity `1.0`.
- High Jaccard word overlap with a recent excerpt → `update`.
- Partial overlap → `ambiguous`.
- Otherwise → `new`.

Reasons are returned as a string tuple for logs and `draft_extras`.

## Pipeline integration

`scheduler/jobs.py` (summarize step):

1. Builds `combined_text`, fingerprint, loads history, classifies evolution, extracts entities, records co-occurrence.
2. Calls `evaluate_cluster_for_pipeline` (`editorial/cluster_rank.py`). Suppressed clusters increment `skipped_intelligence_suppress` and exit early (no OpenAI call).
3. After a draft is stored and duplicate intel is computed, merges `cluster_intelligence`, `editorial_confidence`, and `headline_quality` into `draft_extras`, then appends `append_event_history` so the next tick can see continuity.

## Persistence layout

Under `RUNTIME_STATE_DIR` (see `app.config`):

- `topic_memory.json` — topic rows keyed by hash of hint.
- `event_history.json` — newest-first excerpts + fingerprints.
- `entity_stats.json` — entity frequencies and pair counts (trimmed).

## Operations

Requires the same environment variables as `load_settings()` (e.g. `OPENAI_API_KEY`, `BOT_TOKEN`, …).

- `python3 -m tools.admin_cli topic-stats`
- `python3 -m tools.admin_cli event-inspect`
- `python3 -m tools.admin_cli trend-report`
- `python3 -m tools.admin_cli export-runtime-report --out …` includes an `editorial_intelligence` block; standalone: `python3 -m tools.admin_cli export-intelligence-report --out …`.

## Tests

See `tests/test_editorial_intelligence_layer.py` for fingerprint stability, evolution classification, and entity normalization cases.
