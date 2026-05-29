"""Long-term editorial identity compression."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models import EditorialIdentityVector, EditorialStyleMemory
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def compress_style_memory(*, top_n: int = 24) -> dict[str, Any]:
    """Roll up successful style rows into identity vector."""
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(EditorialStyleMemory)
                    .order_by(EditorialStyleMemory.avg_engagement.desc())
                    .limit(top_n)
                )
            ).scalars()
        )
        if not rows:
            return {"updated": False}

        vectors = {
            "top_verticals": list({r.vertical for r in rows})[:6],
            "avg_style": round(sum(float(r.style_score) for r in rows) / len(rows), 4),
            "avg_insight": round(sum(float(r.insight_score) for r in rows) / len(rows), 4),
            "dominant_patterns": list({r.headline_pattern for r in rows if r.headline_pattern})[:8],
        }
        now = datetime.now(UTC)
        existing = (
            await session.execute(select(EditorialIdentityVector).where(EditorialIdentityVector.key == "default"))
        ).scalar_one_or_none()
        blob = json.dumps(vectors)
        if existing is None:
            session.add(
                EditorialIdentityVector(
                    key="default",
                    vector_json=blob,
                    sample_count=len(rows),
                    updated_at=now,
                )
            )
        else:
            existing.vector_json = blob
            existing.sample_count = len(rows)
            existing.updated_at = now

    log_event(logger, "identity.memory_compressed", top_n=len(rows))
    return {"updated": True, "vectors": vectors}


async def load_identity_vector() -> dict[str, Any]:
    async with session_scope() as session:
        row = (
            await session.execute(select(EditorialIdentityVector).where(EditorialIdentityVector.key == "default"))
        ).scalar_one_or_none()
    if row is None:
        return {}
    try:
        return json.loads(row.vector_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


async def record_style_memory(
    *,
    vertical: str,
    headline_pattern: str,
    style_score: float,
    insight_score: float,
    engagement_score: float = 0.0,
) -> None:
    async with session_scope() as session:
        q = select(EditorialStyleMemory).where(
            EditorialStyleMemory.vertical == vertical[:32],
            EditorialStyleMemory.headline_pattern == headline_pattern[:48],
        )
        row = (await session.execute(q)).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            session.add(
                EditorialStyleMemory(
                    vertical=vertical[:32],
                    headline_pattern=headline_pattern[:48],
                    style_score=style_score,
                    insight_score=insight_score,
                    avg_engagement=engagement_score,
                    sample_count=1,
                    updated_at=now,
                )
            )
        else:
            n = int(row.sample_count or 0)
            row.style_score = (float(row.style_score) * n + style_score) / (n + 1)
            row.insight_score = (float(row.insight_score) * n + insight_score) / (n + 1)
            row.avg_engagement = (float(row.avg_engagement) * n + engagement_score) / (n + 1)
            row.sample_count = n + 1
            row.updated_at = now
