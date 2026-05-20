# Editorial scoring contract (Phase 2.1)

## Version

- `SCORING_VERSION = "phase2.1-v1"`
- Stored on each `editorial_scores` row, in `draft_extras.editorial_intelligence`, and in structured logs.
- Bump when heuristics or weights change materially.

## Score invariants

All dimension scores use **`0.0 .. 1.0`**:

| Value | Meaning |
|-------|---------|
| `0.0` | Worst / none / lowest confidence |
| `1.0` | Strongest / highest confidence |

`duplicate_confidence`: higher = more duplicate risk (same range).

Normalization: `editorial.scoring.base.normalize_score()`.

## Priority labels

Derived **only** from `publish_priority_score`:

| Label | Threshold |
|-------|-----------|
| HIGH | `>= 0.72` |
| MEDIUM | `>= 0.45` |
| LOW | `< 0.45` |

Constants: `PRIORITY_HIGH_THRESHOLD`, `PRIORITY_MEDIUM_THRESHOLD`.

## Reason taxonomy

- Stable codes: `reason_codes` (e.g. `multi_source_confirmation`)
- Human text: `reasons` via `REASON_CATALOG` — never used as Prometheus labels

## Operator feedback (nullable)

- `operator_feedback_score` — `[0, 1]` when set
- `operator_feedback_label` — short operator tag
- API: `editorial.scoring.operator_feedback.apply_operator_feedback()`

## Composable scorers

Small deterministic modules with explicit weights in `base.py`:

- `quality.py`, `novelty.py`, `trust.py`, `priority.py`
- Orchestrated by `service.compute_editorial_intelligence()`

## Deploy

**Mandatory** before app start when upgrading:

```bash
alembic upgrade head
```

## Metrics cardinality

Allowed: aggregate counters/gauges, fixed `scoring_version` in logs.

Forbidden: raw `reason_codes` or free-text reasons as metric labels.
