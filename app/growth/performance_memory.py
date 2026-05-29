"""Post-performance editorial memory — archetypes, headlines, slots."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models import PerformanceArchetypeMemory
from db.session import session_scope


def _archetype(text: str, topic_bucket: str) -> str:
    low = (text or "").lower()
    if "?" in text[:120]:
        return "question_hook"
    if re.search(r"→|—", text[:200]):
        return "consequence_arrow"
    if len(text.split()) <= 45:
        return "short_pulse"
    if topic_bucket in ("crypto", "breaking"):
        return "velocity_alert"
    return "standard_brief"


def _headline_pattern(text: str) -> str:
    first = (text or "").split("\n", 1)[0][:120]
    if re.search(r"\b(Fed|ECB|BTC|Putin|ЦБ|Путин)\b", first, re.I):
        return "entity_first"
    if ":" in first:
        return "colon_split"
    return "lead_sentence"


async def record_performance_memory(
    *,
    draft_id: int | None,
    content: str,
    topic_bucket: str,
    publish_hour_local: int,
    engagement_score: float,
    virality_score: float,
    headline_variant: str = "",
) -> None:
    archetype = _archetype(content, topic_bucket)
    pattern = headline_variant or _headline_pattern(content)
    async with session_scope() as session:
        q = select(PerformanceArchetypeMemory).where(
            PerformanceArchetypeMemory.archetype == archetype,
            PerformanceArchetypeMemory.headline_pattern == pattern,
            PerformanceArchetypeMemory.topic_bucket == topic_bucket[:32],
        )
        row = (await session.execute(q)).scalar_one_or_none()
        if row is None:
            session.add(
                PerformanceArchetypeMemory(
                    archetype=archetype,
                    headline_pattern=pattern,
                    topic_bucket=(topic_bucket or "general")[:32],
                    publish_hour_local=int(publish_hour_local) % 24,
                    sample_count=1,
                    avg_engagement=float(engagement_score or 0),
                    avg_virality=float(virality_score or 0),
                    last_draft_id=draft_id,
                    extras_json="{}",
                    updated_at=datetime.now(UTC),
                )
            )
        else:
            n = int(row.sample_count or 0)
            row.sample_count = n + 1
            row.avg_engagement = (float(row.avg_engagement) * n + float(engagement_score or 0)) / (n + 1)
            row.avg_virality = (float(row.avg_virality) * n + float(virality_score or 0)) / (n + 1)
            row.publish_hour_local = int(publish_hour_local) % 24
            row.last_draft_id = draft_id
            row.updated_at = datetime.now(UTC)


async def best_archetype_for_topic(topic_bucket: str) -> dict[str, Any]:
    async with session_scope() as session:
        q = (
            select(PerformanceArchetypeMemory)
            .where(PerformanceArchetypeMemory.topic_bucket == (topic_bucket or "general")[:32])
            .order_by(PerformanceArchetypeMemory.avg_engagement.desc())
            .limit(1)
        )
        row = (await session.execute(q)).scalar_one_or_none()
        if row is None:
            return {"archetype": "standard_brief", "headline_pattern": "entity_first", "score": 0.35}
        return {
            "archetype": row.archetype,
            "headline_pattern": row.headline_pattern,
            "score": round(float(row.avg_engagement), 4),
            "hour": int(row.publish_hour_local),
        }
