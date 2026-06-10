"""Persistence for advisor recommendation outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AdvisorRecommendationOutcome


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def outcome_row_to_dict(row: AdvisorRecommendationOutcome) -> dict[str, Any]:
    return {
        "draft_id": int(row.draft_id),
        "post_id": int(row.post_id),
        "recommendation_type": str(row.recommendation_type),
        "adopted": bool(row.adopted),
        "alignment_before": int(row.alignment_before),
        "alignment_after": int(row.alignment_after),
        "actual_err": float(row.actual_err) if row.actual_err is not None else None,
        "actual_forwards": int(row.actual_forwards) if row.actual_forwards is not None else None,
        "actual_engagement": float(row.actual_engagement) if row.actual_engagement is not None else None,
        "actual_virality": float(row.actual_virality) if row.actual_virality is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


async def replace_advisor_outcomes_for_draft(
    session: AsyncSession,
    *,
    draft_id: int,
    outcomes: list[dict[str, Any]],
) -> list[AdvisorRecommendationOutcome]:
    await session.execute(delete(AdvisorRecommendationOutcome).where(AdvisorRecommendationOutcome.draft_id == int(draft_id)))
    rows: list[AdvisorRecommendationOutcome] = []
    now = _utcnow()
    for item in outcomes:
        row = AdvisorRecommendationOutcome(
            draft_id=int(draft_id),
            post_id=int(item.get("post_id") or 0),
            recommendation_type=str(item.get("recommendation_type") or "")[:64],
            adopted=1 if bool(item.get("adopted")) else 0,
            alignment_before=int(item.get("alignment_before") or 0),
            alignment_after=int(item.get("alignment_after") or 0),
            actual_err=float(item["actual_err"]) if item.get("actual_err") is not None else None,
            actual_forwards=int(item["actual_forwards"]) if item.get("actual_forwards") is not None else None,
            actual_engagement=float(item["actual_engagement"]) if item.get("actual_engagement") is not None else None,
            actual_virality=float(item["actual_virality"]) if item.get("actual_virality") is not None else None,
            created_at=now,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def list_advisor_outcomes(
    session: AsyncSession,
    *,
    limit: int = 2000,
    draft_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    q = select(AdvisorRecommendationOutcome).order_by(AdvisorRecommendationOutcome.created_at.desc()).limit(limit)
    if draft_ids:
        q = q.where(AdvisorRecommendationOutcome.draft_id.in_([int(x) for x in draft_ids]))
    rows = list((await session.execute(q)).scalars().all())
    return [outcome_row_to_dict(r) for r in rows]
