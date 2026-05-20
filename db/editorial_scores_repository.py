"""Persistence for ``editorial_scores`` (Phase 2.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EditorialScore
from editorial.scoring.base import SCORING_VERSION, publish_priority_label
from editorial.scoring.explainability import render_reason_labels


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_editorial_scores(session: AsyncSession, row: dict[str, Any]) -> EditorialScore:
    draft_id = int(row["draft_id"])
    existing = await session.scalar(
        select(EditorialScore).where(EditorialScore.draft_id == draft_id)
    )
    fields = {
        "quality_score": float(row.get("quality_score") or 0),
        "novelty_score": float(row.get("novelty_score") or 0),
        "source_trust_score": float(row.get("source_trust_score") or 0),
        "duplicate_confidence": float(row.get("duplicate_confidence") or 0),
        "cluster_importance_score": float(row.get("cluster_importance_score") or 0),
        "publish_priority_score": float(row.get("publish_priority_score") or 0),
        "operator_feedback_score": row.get("operator_feedback_score"),
        "operator_feedback_label": row.get("operator_feedback_label"),
        "scoring_version": str(row.get("scoring_version") or SCORING_VERSION)[:32],
        "reasons_json": str(row.get("reasons_json") or "{}"),
    }
    if existing is None:
        rec = EditorialScore(draft_id=draft_id, created_at=_utcnow(), **fields)
        session.add(rec)
        await session.flush()
        return rec

    for k, v in fields.items():
        setattr(existing, k, v)
    await session.flush()
    return existing


async def get_editorial_scores_for_draft(
    session: AsyncSession,
    draft_id: int,
) -> dict[str, Any] | None:
    row = await session.scalar(select(EditorialScore).where(EditorialScore.draft_id == draft_id))
    if row is None:
        return None
    try:
        reasons_data = json.loads(row.reasons_json or "{}")
    except json.JSONDecodeError:
        reasons_data = {}
    codes = reasons_data.get("reason_codes") if isinstance(reasons_data, dict) else []
    if not isinstance(codes, list):
        codes = []
    labels = reasons_data.get("reasons") if isinstance(reasons_data.get("reasons"), list) else []
    if not labels:
        labels = render_reason_labels([str(c) for c in codes])
    return {
        "scoring_version": row.scoring_version or SCORING_VERSION,
        "quality_score": row.quality_score,
        "novelty_score": row.novelty_score,
        "source_trust_score": row.source_trust_score,
        "duplicate_confidence": row.duplicate_confidence,
        "cluster_importance_score": row.cluster_importance_score,
        "publish_priority_score": row.publish_priority_score,
        "publish_priority": publish_priority_label(row.publish_priority_score),
        "operator_feedback_score": row.operator_feedback_score,
        "operator_feedback_label": row.operator_feedback_label,
        "reason_codes": codes,
        "reasons": labels,
    }
