"""Persistence for post_editorial_features."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PostEditorialFeatures


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bool_int(v: Any) -> int:
    return 1 if bool(v) else 0


def features_to_row_fields(features: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline_length": int(features.get("headline_length") or 0),
        "headline_word_count": int(features.get("headline_word_count") or 0),
        "has_number": _bool_int(features.get("has_number")),
        "has_percent": _bool_int(features.get("has_percent")),
        "has_currency": _bool_int(features.get("has_currency")),
        "has_question": _bool_int(features.get("has_question")),
        "has_colon": _bool_int(features.get("has_colon")),
        "has_quote": _bool_int(features.get("has_quote")),
        "uppercase_ratio": float(features.get("uppercase_ratio") or 0.0),
        "body_length": int(features.get("body_length") or 0),
        "paragraph_count": int(features.get("paragraph_count") or 0),
        "bullet_count": int(features.get("bullet_count") or 0),
        "emoji_count": int(features.get("emoji_count") or 0),
        "link_count": int(features.get("link_count") or 0),
        "source_count": int(features.get("source_count") or 0),
        "content_segment": str(features.get("content_segment") or "general_news")[:32],
        "format_profile": str(features.get("format_profile") or "cb_brief")[:32],
        "virality_tier": str(features.get("virality_tier") or "standard")[:32],
        "features_json": json.dumps(features, ensure_ascii=False),
    }


def editorial_features_row_to_dict(row: PostEditorialFeatures) -> dict[str, Any]:
    out = features_to_row_fields(
        {
            "headline_length": row.headline_length,
            "headline_word_count": row.headline_word_count,
            "has_number": row.has_number,
            "has_percent": row.has_percent,
            "has_currency": row.has_currency,
            "has_question": row.has_question,
            "has_colon": row.has_colon,
            "has_quote": row.has_quote,
            "uppercase_ratio": row.uppercase_ratio,
            "body_length": row.body_length,
            "paragraph_count": row.paragraph_count,
            "bullet_count": row.bullet_count,
            "emoji_count": row.emoji_count,
            "link_count": row.link_count,
            "source_count": row.source_count,
            "content_segment": row.content_segment,
            "format_profile": row.format_profile,
            "virality_tier": row.virality_tier,
        }
    )
    out["draft_id"] = int(row.draft_id)
    for k in ("has_number", "has_percent", "has_currency", "has_question", "has_colon", "has_quote"):
        out[k] = bool(out[k])
    return out


async def upsert_post_editorial_features(
    session: AsyncSession,
    *,
    draft_id: int,
    features: dict[str, Any],
) -> PostEditorialFeatures:
    fields = features_to_row_fields(features)
    existing = await session.scalar(
        select(PostEditorialFeatures).where(PostEditorialFeatures.draft_id == int(draft_id))
    )
    if existing is None:
        row = PostEditorialFeatures(draft_id=int(draft_id), created_at=_utcnow(), **fields)
        session.add(row)
        await session.flush()
        return row
    for k, v in fields.items():
        setattr(existing, k, v)
    await session.flush()
    return existing


async def list_post_editorial_features(
    session: AsyncSession,
    *,
    draft_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    q = select(PostEditorialFeatures)
    if draft_ids:
        q = q.where(PostEditorialFeatures.draft_id.in_([int(x) for x in draft_ids]))
    rows = list((await session.execute(q)).scalars().all())
    return [editorial_features_row_to_dict(r) for r in rows]
