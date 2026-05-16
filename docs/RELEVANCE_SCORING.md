# Relevance scoring (unified, explainable)

Unified cluster relevance lives in `editorial/relevance.py` as `compute_unified_relevance` → `RelevanceBreakdown` with a **0–100** `total` and per-component scores in **0–1**.

## Components

| Signal | Meaning |
|--------|---------|
| `freshness` | Youngest raw post age (exponential decay, ~24h scale) |
| `source_reputation` | Mean channel score from `utils/source_reputation` export (defaults ~0.5 if unknown) |
| `topic_momentum` | Derived from topic memory row hit count (bounded) |
| `entity_importance` | More distinct entities in combined text → slightly higher |
| `novelty` | Inverse of `EventEvolution.continuity_score`, with bumps for `new` / damp for `update` |
| `duplicate_suppression` | Normalized optional draft similarity % (0–1); subtracts from total via negative weight |
| `editorial_preference_boost` | Small boost from `feedback_boost_from_stats` (`editorial/feedback.py`) |

Weights (fixed in code, observable in `to_dict()["weights"]`):

- Positive: freshness, source reputation, topic momentum, entity importance, novelty, editorial preference boost.
- Negative: duplicate suppression (acts as a penalty channel).

The scalar `total` is `50 + 48 * raw_weighted_sum`, clamped to `[0, 100]`.

## Pipeline decision

`editorial/cluster_rank.py` combines:

- Topic **saturation** and **cooldown** (`topic_memory.py`),
- The unified relevance total,
- Evolution kind (`new` / `update` / `ambiguous`),

to set `ClusterPipelineDecision.suppress` with explicit `suppression_reasons` (strings) and `ranking_notes`.

## Debugging

```bash
python3 -m tools.admin_cli --json relevance-debug
python3 -m tools.admin_cli relevance-debug --evolution update --continuity 0.62 --duplicate-pct 91
```

(Глобальный флаг `--json` задаётся **до** имени подкоманды, как у остальных команд этого CLI.)

## Draft extras

Published path merges `cluster_intelligence.pipeline_decision` including the full relevance breakdown for moderation UIs and offline analytics.

## Tests

Ranking and duplicate-suppression behavior are covered in `tests/test_editorial_intelligence_layer.py`.
