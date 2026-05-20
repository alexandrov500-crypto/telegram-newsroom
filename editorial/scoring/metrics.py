"""Editorial scoring Prometheus-style counters (in-process)."""

from __future__ import annotations

from editorial.scoring.base import SCORING_VERSION
from editorial.scoring.models import EditorialIntelligenceScores
from utils.metrics import inc, set_gauge

SCORED_ARTICLES_TOTAL = "scored_articles_total"
SCORING_FAILURES_TOTAL = "scoring_failures_total"
AVERAGE_QUALITY_SCORE = "average_quality_score"
AVERAGE_NOVELTY_SCORE = "average_novelty_score"

_sum_quality = 0.0
_sum_novelty = 0.0
_count_scores = 0


def record_scoring_success(scores: EditorialIntelligenceScores) -> None:
    """Aggregate counters only — never attach reason codes/text as metric labels."""
    global _sum_quality, _sum_novelty, _count_scores
    inc(SCORED_ARTICLES_TOTAL)
    # Fixed low-cardinality version marker (not per-reason labels).
    set_gauge("editorial_scoring_version_epoch", 1.0 if scores.scoring_version == SCORING_VERSION else 0.0)
    _count_scores += 1
    _sum_quality += scores.quality_score
    _sum_novelty += scores.novelty_score
    if _count_scores > 0:
        set_gauge(AVERAGE_QUALITY_SCORE, _sum_quality / _count_scores)
        set_gauge(AVERAGE_NOVELTY_SCORE, _sum_novelty / _count_scores)


def record_scoring_failure() -> None:
    inc(SCORING_FAILURES_TOTAL)


def reset_scoring_metrics_for_tests() -> None:
    global _sum_quality, _sum_novelty, _count_scores
    _sum_quality = 0.0
    _sum_novelty = 0.0
    _count_scores = 0
