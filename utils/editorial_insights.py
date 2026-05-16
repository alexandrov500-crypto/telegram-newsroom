from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Draft, DraftStatus, PublishedPost


def _utc_day_start(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_sources(sources: str | None) -> list[dict[str, Any]]:
    if not sources:
        return []
    try:
        data = json.loads(sources)
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _extras_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def collect_editorial_insights(session: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    """
    DB-backed editorial snapshot (bounded queries, deterministic ordering in aggregates).
    """
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    day0 = _utc_day_start(when)
    since24 = when - timedelta(hours=24)

    pending_n = int(
        await session.scalar(select(func.count()).select_from(Draft).where(Draft.status == DraftStatus.PENDING.value))
        or 0
    )
    oldest_row = await session.scalar(
        select(Draft.created_at)
        .where(Draft.status == DraftStatus.PENDING.value)
        .order_by(Draft.created_at.asc(), Draft.id.asc())
        .limit(1)
    )
    oldest_hours: float | None = None
    if oldest_row is not None:
        orow = oldest_row if oldest_row.tzinfo else oldest_row.replace(tzinfo=timezone.utc)
        oldest_hours = round(max(0.0, (when - orow.astimezone(timezone.utc)).total_seconds()) / 3600.0, 2)

    stmt_recent = (
        select(Draft)
        .where(Draft.created_at >= day0)
        .order_by(Draft.created_at.desc(), Draft.id.desc())
        .limit(120)
    )
    recent_drafts = list((await session.execute(stmt_recent)).scalars().all())

    stmt_dup_scan = (
        select(Draft)
        .where(Draft.created_at >= since24)
        .order_by(Draft.created_at.desc(), Draft.id.desc())
        .limit(120)
    )
    dup_scan = list((await session.execute(stmt_dup_scan)).scalars().all())
    dup_wave = 0
    for d in dup_scan:
        exd = _extras_obj(d.draft_extras)
        dup = exd.get("duplicate_intel") if isinstance(exd.get("duplicate_intel"), dict) else {}
        if float(dup.get("max_similarity_pct") or 0.0) >= 92.0:
            dup_wave += 1

    src_counter: Counter[str] = Counter()
    cat_counter: Counter[str] = Counter()
    token_counter: Counter[str] = Counter()
    for d in recent_drafts:
        for s in _parse_sources(d.sources):
            ch = str(s.get("channel", "")).strip()
            if ch:
                src_counter[ch] += 1
        ex = _extras_obj(d.draft_extras)
        cat = ex.get("category")
        if isinstance(cat, str) and cat.strip():
            cat_counter[cat.strip()] += 1
        head = (d.content or "").splitlines()[0].strip() if (d.content or "").splitlines() else ""
        for w in re.findall(r"[a-zA-Z\u0400-\u04FF]{4,24}", head.lower()):
            if w in {"this", "that", "with", "from", "have", "been", "will", "your", "their"}:
                continue
            token_counter[w] += 1

    pub_day = int(
        await session.scalar(
            select(func.count())
            .select_from(PublishedPost)
            .where(PublishedPost.published_at >= day0)
        )
        or 0
    )
    hours_elapsed = max(1.0, (when - day0).total_seconds() / 3600.0)
    publish_velocity = round(pub_day / hours_elapsed, 4)

    top_sources = [{"channel": k, "count": int(v)} for k, v in src_counter.most_common(8)]
    trending_topics = [{"term": k, "count": int(v)} for k, v in token_counter.most_common(12)]
    category_distribution = [{"category": k, "count": int(v)} for k, v in sorted(cat_counter.items(), key=lambda kv: (-kv[1], kv[0]))]

    bottleneck = "unknown"
    if pending_n >= 18:
        bottleneck = "high_pending_volume"
    elif oldest_hours is not None and oldest_hours >= 72:
        bottleneck = "stale_pending_tail"
    elif dup_wave >= 6:
        bottleneck = "duplicate_review_load"
    else:
        bottleneck = "nominal"

    return {
        "as_of": when.isoformat(),
        "pending_count": pending_n,
        "oldest_pending_age_hours": oldest_hours,
        "top_sources_today": top_sources,
        "trending_topics": trending_topics,
        "duplicate_waves_24h": dup_wave,
        "publish_velocity_per_hour": publish_velocity,
        "publishes_today": pub_day,
        "category_distribution_today": category_distribution,
        "moderation_bottleneck_hint": bottleneck,
    }
