"""Persistence for post_growth_validation (Growth Validation Layer)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.validation.status import ValidationStatus
from db.models import PostGrowthValidation


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def upsert_post_growth_validation_publish(
    session: AsyncSession,
    *,
    draft_id: int,
    telegram_post_id: int,
    published_at: datetime,
    format_profile: str,
    predicted_virality: int,
    virality_tier: str,
    topic_bucket: str,
    primary_source: str,
    experiment_json: str,
    channel_id: int = 0,
    content_segment: str = "general_news",
) -> PostGrowthValidation:
    existing = await session.scalar(
        select(PostGrowthValidation).where(PostGrowthValidation.draft_id == int(draft_id))
    )
    fields = {
        "telegram_post_id": int(telegram_post_id),
        "channel_id": int(channel_id),
        "published_at": published_at,
        "format_profile": str(format_profile)[:32],
        "predicted_virality": int(predicted_virality),
        "virality_tier": str(virality_tier)[:32],
        "topic_bucket": str(topic_bucket)[:64],
        "primary_source": str(primary_source)[:255],
        "experiment_json": experiment_json,
        "content_segment": str(content_segment)[:32],
        "validation_status": ValidationStatus.PENDING.value,
    }
    if existing is None:
        row = PostGrowthValidation(draft_id=int(draft_id), created_at=_utcnow(), **fields)
        session.add(row)
        await session.flush()
        return row
    for k, v in fields.items():
        if k == "validation_status" and existing.validation_status == ValidationStatus.FINAL.value:
            continue
        setattr(existing, k, v)
    await session.flush()
    return existing


async def update_post_growth_validation_actuals(
    session: AsyncSession,
    *,
    draft_id: int,
    actuals_json: str,
    validated_at: datetime,
    prefer_label: str = "t24h",
    validation_status: str | None = None,
) -> PostGrowthValidation | None:
    row = await session.scalar(
        select(PostGrowthValidation).where(PostGrowthValidation.draft_id == int(draft_id))
    )
    if row is None:
        return None
    incoming = _parse_json(actuals_json)
    existing = _parse_json(row.actuals_json)
    if existing:
        prev_label = str(existing.get("snapshot_label") or "")
        if prev_label == "t24h" and prefer_label != "t24h":
            return row
    merged = {**existing, **incoming}
    row.actuals_json = json.dumps(merged, ensure_ascii=False)
    if validation_status:
        row.validation_status = validation_status
    if validation_status == ValidationStatus.FINAL.value:
        row.validated_at = validated_at
    await session.flush()
    return row


def validation_row_to_dict(row: PostGrowthValidation) -> dict[str, Any]:
    experiment = _parse_json(row.experiment_json)
    actuals = _parse_json(row.actuals_json)
    out: dict[str, Any] = {
        "draft_id": int(row.draft_id),
        "telegram_post_id": int(row.telegram_post_id),
        "published_at": row.published_at.isoformat() if row.published_at else "",
        "format_profile": str(row.format_profile),
        "predicted_virality": int(row.predicted_virality),
        "virality_tier": str(row.virality_tier),
        "topic_bucket": str(row.topic_bucket),
        "primary_source": str(row.primary_source),
        "content_segment": str(row.content_segment or "general_news"),
        "validation_status": str(row.validation_status or ValidationStatus.PENDING.value),
    }
    out.update(experiment)
    out.update(actuals)
    return out


async def get_post_growth_validation_by_draft(
    session: AsyncSession,
    draft_id: int,
) -> PostGrowthValidation | None:
    return await session.scalar(
        select(PostGrowthValidation).where(PostGrowthValidation.draft_id == int(draft_id))
    )


async def list_post_growth_validation(
    session: AsyncSession,
    *,
    limit: int = 100,
    since_days: int | None = None,
    validated_only: bool = False,
    final_only: bool = False,
) -> list[dict[str, Any]]:
    q = select(PostGrowthValidation).order_by(PostGrowthValidation.published_at.desc())
    if since_days is not None:
        cutoff = _utcnow() - timedelta(days=int(since_days))
        q = q.where(PostGrowthValidation.published_at >= cutoff)
    if final_only:
        q = q.where(PostGrowthValidation.validation_status == ValidationStatus.FINAL.value)
    elif validated_only:
        q = q.where(PostGrowthValidation.validated_at.is_not(None))
    q = q.limit(max(1, int(limit)))
    rows = list((await session.execute(q)).scalars().all())
    return [validation_row_to_dict(r) for r in rows]
