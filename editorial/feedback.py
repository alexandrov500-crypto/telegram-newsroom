"""Adaptive heuristics from editorial actions (DB-backed aggregates)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Draft, DraftStatus


async def collect_editorial_feedback_stats(session: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    since7 = when - timedelta(days=7)

    async def count_status(st: str) -> int:
        q = select(func.count()).select_from(Draft).where(Draft.status == st)
        r = await session.execute(q)
        return int(r.scalar_one() or 0)

    pending = await count_status(DraftStatus.PENDING.value)
    published = await count_status(DraftStatus.PUBLISHED.value)
    rejected = await count_status(DraftStatus.REJECTED.value)

    q_recent = (
        select(Draft)
        .where(Draft.created_at >= since7)
        .order_by(Draft.created_at.desc())
        .limit(200)
    )
    recent = list((await session.execute(q_recent)).scalars().all())
    edits = sum(1 for d in recent if (d.edit_history or "[]") not in ("[]", "", "null"))

    return {
        "schema_version": 1,
        "counts": {"pending": pending, "published": published, "rejected": rejected},
        "recent_window_days": 7,
        "recent_drafts_sampled": len(recent),
        "manual_edit_signals": edits,
        "acceptance_proxy": round(
            published / max(1, published + rejected),
            4,
        ),
    }


def feedback_boost_from_stats(stats: dict[str, Any] | None) -> float:
    """Map aggregate stats to a small boost for relevance (bounded)."""
    if not stats:
        return 0.0
    pub = float((stats.get("counts") or {}).get("published") or 0)
    rej = float((stats.get("counts") or {}).get("rejected") or 0)
    acc = pub / max(1.0, pub + rej)
    return round(max(0.0, min(0.2, (acc - 0.5) * 0.25)), 4)
