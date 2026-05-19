from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

_MAX_VIEWS = 50_000
_MAX_FORWARDS = 2_000
_MAX_REACTIONS = 1_000

_WEIGHT_VIEWS = 0.35
_WEIGHT_FORWARDS = 0.30
_WEIGHT_REACTIONS = 0.20
_WEIGHT_TRUST = 0.10
_WEIGHT_VIRALITY = 0.05

_HIGH_PERFORMING_THRESHOLD = 0.75
_SPAM_VIEW_RATIO = 500


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalize_count(value: int, cap: int) -> float:
    if value <= 0 or cap <= 0:
        return 0.0
    return _clamp(math.log1p(value) / math.log1p(cap))


def calculate_engagement_score(
    *,
    views: int = 0,
    forwards: int = 0,
    reactions: int = 0,
    source_trust: float = 0.5,
    topic_virality: float = 0.5,
) -> float:
    """
    Weighted engagement score normalized to 0.0–1.0.
    Penalizes suspicious view-heavy / low-interaction patterns.
    """
    view_norm = _normalize_count(max(views, 0), _MAX_VIEWS)
    forward_norm = _normalize_count(max(forwards, 0), _MAX_FORWARDS)
    reaction_norm = _normalize_count(max(reactions, 0), _MAX_REACTIONS)
    trust = _clamp(float(source_trust))
    virality = _clamp(float(topic_virality))

    raw = (
        _WEIGHT_VIEWS * view_norm
        + _WEIGHT_FORWARDS * forward_norm
        + _WEIGHT_REACTIONS * reaction_norm
        + _WEIGHT_TRUST * trust
        + _WEIGHT_VIRALITY * virality
    )

    if views > _SPAM_VIEW_RATIO and forwards + reactions < 3:
        raw *= 0.85
        logger.info(
            "event=adaptive_signal_detected reason=low_interaction_high_views views=%d",
            views,
        )

    score = _clamp(raw)
    if score >= _HIGH_PERFORMING_THRESHOLD:
        logger.info(
            "event=high_performing_post_detected score=%.3f views=%d forwards=%d reactions=%d",
            score,
            views,
            forwards,
            reactions,
        )
    return score
