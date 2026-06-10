"""Persistence for draft_growth_scores (Growth Layer Phase 1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.virality.engine import ViralityScoreResult
from db.models import DraftGrowthScore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_draft_growth_score(
    session: AsyncSession,
    *,
    draft_id: int,
    result: ViralityScoreResult,
    format_profile: str,
) -> DraftGrowthScore:
    existing = await session.scalar(select(DraftGrowthScore).where(DraftGrowthScore.draft_id == int(draft_id)))
    dims = result.dimensions
    fields = {
        "virality_score": int(result.score),
        "virality_tier": str(result.tier.value),
        "novelty": float(dims.get("novelty") or 0.0),
        "economic_impact": float(dims.get("economic_impact") or 0.0),
        "audience_relevance": float(dims.get("audience_relevance") or 0.0),
        "emotional_trigger": float(dims.get("emotional_trigger") or 0.0),
        "shareability": float(dims.get("shareability") or 0.0),
        "format_profile": str(format_profile)[:32],
        "reasons_json": json.dumps(list(result.reasons), ensure_ascii=False),
        "model_version": str(result.model_version)[:32],
        "computed_at": _utcnow(),
    }
    if existing is None:
        row = DraftGrowthScore(draft_id=int(draft_id), **fields)
        session.add(row)
        await session.flush()
        return row
    for k, v in fields.items():
        setattr(existing, k, v)
    await session.flush()
    return existing


async def get_draft_growth_score(session: AsyncSession, draft_id: int) -> DraftGrowthScore | None:
    return await session.scalar(select(DraftGrowthScore).where(DraftGrowthScore.draft_id == int(draft_id)))


def growth_score_to_dict(row: DraftGrowthScore) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        parsed = json.loads(row.reasons_json or "[]")
        if isinstance(parsed, list):
            reasons = [str(x) for x in parsed[:8]]
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "virality_score": int(row.virality_score),
        "virality_tier": str(row.virality_tier),
        "format_profile": str(row.format_profile),
        "dimensions": {
            "novelty": float(row.novelty),
            "economic_impact": float(row.economic_impact),
            "audience_relevance": float(row.audience_relevance),
            "emotional_trigger": float(row.emotional_trigger),
            "shareability": float(row.shareability),
        },
        "reasons": reasons,
        "model_version": str(row.model_version),
    }
