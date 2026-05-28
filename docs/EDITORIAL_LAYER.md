# Editorial layer vs runtime layer

## Safe to change (cosmetic / editorial)

- `SUMMARY_STYLE`, `HEADLINE_MODE`, tone prompts (`ai/editorial.py`)
- `publisher/formatting.py`, `operator_ui_ru.py`
- Desk thresholds (`DESK_MIN_*`) — **behavioral** but not infrastructure
- Source display policy (`PUBLISH_INCLUDE_SOURCES`, `SOURCE_MENTIONS_IN_POST`)
- Precluster tuning (`CLUSTER_*`, `PRECLUSTER_*`)

## Frozen (runtime — Phase 3)

- `RUNTIME_NODE_ROLE`, execution lease, singleton guard
- `failed_drafts` retry engine
- `pipeline_ticks`, stuck detection
- Publish idempotency + `publish_journal`
- `/health` schema, `newsroom` CLI commands
- `auto_maintenance` publish halt semantics

## Rule

If a change touches **both** layers, split into two PRs: editorial first, runtime only when required.
