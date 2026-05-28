"""Breaking injection — high-score items bypass normal batching."""

from __future__ import annotations

import logging
from typing import Any

from app.editorial.ranking import EditorialRankScore
from app.observability import editorial_metrics as em
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_BREAKING_THRESHOLD = 0.75
_HIGH_THRESHOLD = 0.5


def breaking_threshold() -> float:
    import os

    raw = os.getenv("EDITORIAL_BREAKING_THRESHOLD", "0.75").strip()
    try:
        return float(raw)
    except ValueError:
        return _BREAKING_THRESHOLD


def high_threshold() -> float:
    import os

    raw = os.getenv("EDITORIAL_HIGH_THRESHOLD", "0.5").strip()
    try:
        return float(raw)
    except ValueError:
        return _HIGH_THRESHOLD


def should_inject_breaking(score: EditorialRankScore) -> bool:
    return score.final_score > breaking_threshold()


def enrich_item_for_lane(item: dict[str, Any], score: EditorialRankScore) -> dict[str, Any]:
    """Attach ranking metadata and breaking-stream flag for downstream consumers."""
    out = {
        **item,
        "editorial_rank": score.to_dict(),
        "editorial_final_score": score.final_score,
    }
    if should_inject_breaking(score):
        out["is_breaking_stream"] = True
        out["breaking_injected"] = True
        em.record_breaking_item()
        log_event(
            logger,
            "breaking.inject",
            news_id=item.get("news_id"),
            final_score=score.final_score,
            breaking=score.breaking,
        )
    elif score.final_score > high_threshold():
        em.record_high_score_item()
    return out


def route_to_breaking(item: dict[str, Any], score: EditorialRankScore) -> dict[str, Any]:
    """Mark item for breaking pipeline (caller enqueues on breaking queue)."""
    return enrich_item_for_lane({**item, "lane_priority": "breaking"}, score)
