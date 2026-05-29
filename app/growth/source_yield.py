"""Source yield intelligence — ROI beyond trust score."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from db.models import PostPerformance, SourceRegistryEntry
from db.session import session_scope


def _enabled() -> bool:
    return os.getenv("GROWTH_SOURCE_YIELD_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


async def refresh_source_yield_scores(*, window_days: int = 14) -> int:
    """Recompute yield_score on source_registry from post_performance."""
    if not _enabled():
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    stats: dict[str, dict[str, float]] = {}

    async with session_scope() as session:
        q = (
            select(
                PostPerformance.primary_source,
                func.count(PostPerformance.id),
                func.avg(PostPerformance.engagement_score),
                func.avg(PostPerformance.virality_score),
            )
            .where(
                PostPerformance.snapshot_at >= cutoff,
                PostPerformance.primary_source != "",
            )
            .group_by(PostPerformance.primary_source)
        )
        for src, cnt, avg_eng, avg_vir in (await session.execute(q)).all():
            handle = str(src or "").strip().lower().lstrip("@")
            if not handle:
                continue
            stats[handle] = {
                "posts": float(cnt or 0),
                "engagement": float(avg_eng or 0),
                "virality": float(avg_vir or 0),
            }

        rows = list((await session.execute(select(SourceRegistryEntry))).scalars().all())
        updated = 0
        for row in rows:
            h = (row.handle or "").strip().lower().lstrip("@")
            st = stats.get(h, {})
            posts = float(st.get("posts") or 0)
            eng = float(st.get("engagement") or 0)
            vir = float(st.get("virality") or 0)
            yield_score = round(0.55 * eng + 0.35 * vir + 0.1 * min(1.0, posts / 10.0), 4)
            try:
                ex = json.loads(row.extras_json or "{}")
            except (json.JSONDecodeError, TypeError):
                ex = {}
            ex["yield_score"] = yield_score
            ex["yield_posts"] = int(posts)
            ex["yield_updated_at"] = datetime.now(UTC).isoformat()
            row.extras_json = json.dumps(ex)

            if posts >= 3 and yield_score < 0.22 and row.status == "active":
                row.status = "probation"
                row.fail_streak = int(row.fail_streak or 0) + 1
            elif posts >= 5 and yield_score >= 0.55 and row.status == "probation":
                row.status = "active"
                row.fail_streak = 0
            elif yield_score >= 0.62 and row.tier in ("T2", "T3") and posts >= 8:
                row.tier = {"T3": "T2", "T2": "T1"}.get(row.tier, row.tier)
            elif yield_score < 0.18 and posts >= 6 and row.tier != "T4":
                row.tier = {"T0": "T1", "T1": "T2", "T2": "T3"}.get(row.tier, "T4")

            row.updated_at = datetime.now(UTC)
            updated += 1
    return updated
