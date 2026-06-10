"""Persistence for pre-publication growth advice (validation loop)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DraftGrowthAdvice


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def advice_to_row_fields(advice: dict[str, Any]) -> dict[str, Any]:
    alignment = advice.get("alignment") if isinstance(advice.get("alignment"), dict) else {}
    return {
        "alignment_score": int(alignment.get("score") or 0),
        "headline_alignment": int(alignment.get("headline_alignment") or 0),
        "structure_alignment": int(alignment.get("structure_alignment") or 0),
        "segment_alignment": int(alignment.get("segment_alignment") or 0),
        "predicted_segment": str(advice.get("segment") or "general_news")[:32],
        "recommendations_json": json.dumps(
            {
                "recommendations": advice.get("recommendations") or [],
                "recommendations_detailed": advice.get("recommendations_detailed") or [],
                "mismatches": advice.get("mismatches") or [],
                "features": advice.get("features") or {},
                "alignment": alignment,
                "sample_size": advice.get("sample_size"),
                "data_source": advice.get("data_source"),
                "computed_at": advice.get("computed_at"),
            },
            ensure_ascii=False,
        ),
    }


def growth_advice_row_to_dict(row: DraftGrowthAdvice) -> dict[str, Any]:
    try:
        payload = json.loads(row.recommendations_json or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return {
        "draft_id": int(row.draft_id),
        "alignment_score": int(row.alignment_score),
        "headline_alignment": int(row.headline_alignment),
        "structure_alignment": int(row.structure_alignment),
        "segment_alignment": int(row.segment_alignment),
        "predicted_segment": str(row.predicted_segment),
        "recommendations": payload.get("recommendations") or [],
        "recommendations_detailed": payload.get("recommendations_detailed") or [],
        "mismatches": payload.get("mismatches") or [],
        "features": payload.get("features") or {},
        "computed_at": row.created_at.isoformat() if row.created_at else "",
        "sample_size": payload.get("sample_size"),
        "data_source": payload.get("data_source"),
    }


async def upsert_draft_growth_advice(
    session: AsyncSession,
    *,
    draft_id: int,
    advice: dict[str, Any],
) -> DraftGrowthAdvice:
    fields = advice_to_row_fields(advice)
    existing = await session.scalar(select(DraftGrowthAdvice).where(DraftGrowthAdvice.draft_id == int(draft_id)))
    if existing is None:
        row = DraftGrowthAdvice(draft_id=int(draft_id), created_at=_utcnow(), **fields)
        session.add(row)
        await session.flush()
        return row
    for k, v in fields.items():
        setattr(existing, k, v)
    await session.flush()
    return existing


async def list_draft_growth_advice(
    session: AsyncSession,
    *,
    draft_ids: list[int] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    q = select(DraftGrowthAdvice).order_by(DraftGrowthAdvice.created_at.desc()).limit(limit)
    if draft_ids:
        q = q.where(DraftGrowthAdvice.draft_id.in_([int(x) for x in draft_ids]))
    rows = list((await session.execute(q)).scalars().all())
    return [growth_advice_row_to_dict(r) for r in rows]


async def get_draft_growth_advice(session: AsyncSession, draft_id: int) -> dict[str, Any] | None:
    row = await session.scalar(select(DraftGrowthAdvice).where(DraftGrowthAdvice.draft_id == int(draft_id)))
    return growth_advice_row_to_dict(row) if row is not None else None
