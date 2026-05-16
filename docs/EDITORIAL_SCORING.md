# Editorial scoring (rule-based)

The **`editorial/`** package adds deterministic signals for moderation UX and future ranking — **no ML models** in this milestone.

## `editorial/scoring.py`

`compute_editorial_score_card(...)` returns an `EditorialScoreCard` (`editorial/models.py`) with scores in `[0, 1]`:

| Field | Intent |
|-------|--------|
| `freshness` | From age of source `RawPost.created_at` |
| `source_reliability` | Channel diversity + cluster size heuristic |
| `topic_importance` | Length / cluster richness proxy |
| `spam_likelihood` | Keyword / punctuation spam cues |
| `duplicate_confidence` | Inverse of quality uniqueness |
| `ai_confidence_estimate` | Blend of quality heuristics + length |

Results are merged into `draft_extras["editorial_scores"]` when a draft is created in `scheduler/jobs.py`.

## Semantic similarity foundation

`editorial/similarity.py` defines:

- `SimilarityBackend` protocol (`async def similarity(a, b) -> float`).
- `LexicalJaccardSimilarity` — default token Jaccard on normalized text.
- `normalize_for_similarity` — deterministic lowercasing / whitespace fold.

Swap the backend later for embeddings **without** changing call sites that adopt the protocol.

## Relationship to existing dedupe

Scheduler duplicate detection still uses lexical/hash logic in `db.repository` / `scheduler` helpers. Editorial scores **complement** that path; they do not replace DB dedupe.
