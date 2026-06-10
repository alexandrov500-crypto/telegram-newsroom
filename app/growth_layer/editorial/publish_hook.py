"""Record editorial features at publish time."""

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.editorial.feature_extraction import draft_to_post_dict, extract_editorial_features
from app.growth_layer.segments.content_segments import classify_content_segment
from db.editorial_features_repository import upsert_post_editorial_features
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("GROWTH_EDITORIAL_INTELLIGENCE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def record_editorial_features(
    session: AsyncSession,
    *,
    draft_id: int,
    content: str,
    sources: str,
    draft_extras: str | None,
    editor_title: str | None = None,
    editor_summary: str | None = None,
    format_profile: str = "",
    virality_tier: str = "",
    topic_bucket: str = "",
) -> None:
    if not _enabled():
        return
    segment = classify_content_segment(
        {"draft_extras": draft_extras, "topic_bucket": topic_bucket, "category": topic_bucket}
    )
    post = draft_to_post_dict(
        draft_id=int(draft_id),
        content=content,
        sources=sources,
        draft_extras=draft_extras,
        editor_title=editor_title,
        editor_summary=editor_summary,
        content_segment=segment,
        format_profile=format_profile,
        virality_tier=virality_tier,
    )
    features = extract_editorial_features(post)
    await upsert_post_editorial_features(session, draft_id=int(draft_id), features=features)
    log_event(logger, "growth.editorial.features_recorded", draft_id=draft_id, segment=segment)
