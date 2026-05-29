"""Bridge measured post metrics into trend_memory (replaces proxy-only signals)."""

from __future__ import annotations

import json
import os

from app.analytics.engagement_scoring import metrics_to_trend_memory_payload
from db.session import session_scope
from sqlalchemy import select
from db.models import Draft


async def feed_real_metrics_to_trend_memory(
    *,
    draft_id: int,
    topic_bucket: str,
    metrics: dict,
) -> None:
    runtime_dir = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    async with session_scope() as session:
        draft = (await session.execute(select(Draft).where(Draft.id == int(draft_id)))).scalar_one_or_none()
        text = str(draft.content or "")[:800] if draft else ""
    payload = metrics_to_trend_memory_payload(metrics)
    from app.editorial.intelligence.trend_memory import observe_narrative_event

    observe_narrative_event(
        runtime_dir,
        text=text,
        category=topic_bucket,
        repost_rate=payload["repost_rate"],
        forward_velocity=payload["forward_velocity"],
        open_retention=payload["open_retention"],
        reaction_density=payload["reaction_density"],
        quoteability=payload["quoteability"],
        screenshot_probability=payload["screenshot_probability"],
        engagement_longevity=payload["engagement_longevity"],
        hashtags=[],
        hook_variant="real_metrics",
    )
