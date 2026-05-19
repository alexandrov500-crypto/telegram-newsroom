from __future__ import annotations

from bot.editorial.memory.saturation import hours_since
from bot.editorial.memory.types import (
    FOLLOW_UP_DUPLICATE,
    FOLLOW_UP_FOLLOW,
    FOLLOW_UP_HISTORICAL,
    FOLLOW_UP_MINOR,
    FOLLOW_UP_NEW,
    StorylineSnapshot,
)
from bot.editorial.quality.phrases import jaccard_similarity


def classify_follow_up(
    *,
    match_score: float,
    storyline: StorylineSnapshot | None,
    headline: str,
    summary: str | None,
) -> str:
    if storyline is None or storyline.publish_count == 0:
        return FOLLOW_UP_NEW

    text_score = jaccard_similarity(
        headline,
        storyline.latest_headline or storyline.title,
    )
    if summary and storyline.latest_summary:
        text_score = max(text_score, jaccard_similarity(summary, storyline.latest_summary))

    hours = hours_since(storyline.last_updated_at)

    if text_score >= 0.88 or match_score >= 0.9:
        return FOLLOW_UP_DUPLICATE
    if text_score >= 0.72:
        return FOLLOW_UP_MINOR
    if hours >= 168 and match_score >= 0.35:
        return FOLLOW_UP_HISTORICAL
    if match_score >= 0.42 or text_score >= 0.45:
        return FOLLOW_UP_FOLLOW
    return FOLLOW_UP_NEW
