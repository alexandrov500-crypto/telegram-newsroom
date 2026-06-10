"""Record advisor recommendation outcomes after publish validation."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.advisor_validation.adoption import detect_recommendation_adoption
from app.growth_layer.editorial.feature_extraction import draft_to_post_dict, extract_editorial_features
from app.growth_layer.prepublish.growth_advisor import evaluate_growth_alignment
from db.advisor_outcomes_repository import replace_advisor_outcomes_for_draft
from db.growth_advice_repository import get_draft_growth_advice
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("GROWTH_ADVISOR_VALIDATION_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


async def record_advisor_outcomes_for_draft(
    session: AsyncSession,
    *,
    draft_id: int,
    telegram_post_id: int,
    content: str,
    sources: str = "[]",
    draft_extras: str | None = None,
    editor_title: str | None = None,
    editor_summary: str | None = None,
    actuals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Detect adoption and persist one outcome row per recommendation.
    Called when validation actuals are FINAL (t24h).
    """
    if not _enabled():
        return []

    advice_row = await get_draft_growth_advice(session, int(draft_id))
    if not advice_row:
        return []

    advice = {
        "features": advice_row.get("features") or {},
        "recommendations_detailed": advice_row.get("recommendations_detailed") or [],
        "mismatches": advice_row.get("mismatches") or [],
        "alignment": {
            "score": advice_row.get("alignment_score"),
            "headline_alignment": advice_row.get("headline_alignment"),
            "structure_alignment": advice_row.get("structure_alignment"),
            "segment_alignment": advice_row.get("segment_alignment"),
        },
        "segment": advice_row.get("predicted_segment"),
    }

    if not advice["recommendations_detailed"]:
        return []

    published_post = draft_to_post_dict(
        draft_id=int(draft_id),
        content=content,
        sources=sources,
        draft_extras=draft_extras,
        editor_title=editor_title,
        editor_summary=editor_summary,
        content_segment=str(advice_row.get("predicted_segment") or ""),
    )
    published_features = extract_editorial_features(published_post)
    draft_features = advice_row.get("features") or advice.get("features") or {}

    adoptions = detect_recommendation_adoption(advice, published_features, draft_features=draft_features)
    if not adoptions:
        return []

    alignment_after = evaluate_growth_alignment(published_post)
    alignment_before = int(advice_row.get("alignment_score") or 0)
    actuals = actuals or {}

    outcome_rows: list[dict[str, Any]] = []
    for item in adoptions:
        outcome_rows.append(
            {
                "draft_id": int(draft_id),
                "post_id": int(telegram_post_id),
                "recommendation_type": str(item.get("recommendation_type") or item.get("recommendation")),
                "adopted": bool(item.get("adopted")),
                "alignment_before": alignment_before,
                "alignment_after": int(alignment_after.get("score") or 0),
                "actual_err": actuals.get("actual_err"),
                "actual_forwards": actuals.get("actual_forwards"),
                "actual_engagement": actuals.get("actual_engagement"),
                "actual_virality": actuals.get("actual_virality_score") or actuals.get("actual_virality"),
            }
        )

    await replace_advisor_outcomes_for_draft(session, draft_id=int(draft_id), outcomes=outcome_rows)
    log_event(
        logger,
        "growth.advisor.outcomes_recorded",
        draft_id=draft_id,
        recommendations=len(outcome_rows),
        adopted=sum(1 for r in outcome_rows if r.get("adopted")),
    )
    return outcome_rows
