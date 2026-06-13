"""Weekly growth summary for operator Telegram."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from db.models import ChannelAudienceSnapshot, PostPerformance, PublishedPost
from db.session import session_scope


def format_weekly_growth_report(summary: dict[str, Any]) -> str:
    lines = [
        "📊 Weekly Growth Report",
        f"Posts: {summary.get('published_7d')} ({summary.get('avg_per_day')}/day)",
    ]
    aud = summary.get("audience") or {}
    if aud.get("member_count") is not None:
        lines.append(
            f"Subs: {aud['member_count']} (Δ7d {aud.get('delta_7d', 0):+d})"
        )
    lines.append(f"Engagement avg: {summary.get('avg_engagement', 'n/a')}")
    lines.append(f"Health: {summary.get('health_score')} · momentum {summary.get('momentum')}")

    tops = summary.get("top_topics") or []
    if tops:
        lines.append("Top topics: " + ", ".join(str(t.get("topic")) for t in tops[:3]))

    prom = summary.get("sources_promoted") or []
    if prom:
        lines.append("⭐ Promoted: " + ", ".join(f"@{p.get('handle', '').lstrip('@')}" for p in prom[:3]))

    recs = summary.get("recommendations") or []
    for r in recs[:3]:
        lines.append(f"→ {r}")
    return "\n".join(lines)


async def build_weekly_growth_summary(
    *,
    runtime_dir: str,
    channel_id: int | None,
    pulse: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=7)

    async with session_scope() as session:
        pub_7d = int(
            (await session.execute(select(func.count(PublishedPost.id)).where(PublishedPost.published_at >= cutoff))).scalar()
            or 0
        )
        avg_eng = (
            await session.execute(
                select(func.avg(PostPerformance.engagement_score)).where(
                    PostPerformance.snapshot_at >= cutoff,
                    PostPerformance.snapshot_label.in_(("t1h", "t6h", "t24h")),
                )
            )
        ).scalar()

        audience_row = None
        if channel_id:
            audience_row = (
                await session.execute(
                    select(ChannelAudienceSnapshot)
                    .where(ChannelAudienceSnapshot.channel_id == int(channel_id))
                    .order_by(ChannelAudienceSnapshot.captured_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

    topic_matrix: dict[str, Any] = {}
    curation: dict[str, Any] = {}
    try:
        topic_matrix = json.loads((Path(runtime_dir) / "topic_boost_matrix.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    try:
        curation = json.loads((Path(runtime_dir) / "autonomous_fastlane_sources.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    recommendations: list[str] = []
    avg_day = round(pub_7d / 7.0, 1)
    target = float((pulse or {}).get("target_posts_per_day") or 28)
    if avg_day < target * 0.7:
        recommendations.append("throughput below target — robot will relax gates")
    if float((pulse or {}).get("engagement_momentum") or 0) < 0.25:
        recommendations.append("engagement flat — topic boost favors proven themes")

    return {
        "week_start": cutoff.isoformat(),
        "published_7d": pub_7d,
        "avg_per_day": avg_day,
        "avg_engagement": round(float(avg_eng or 0), 3),
        "health_score": (pulse or {}).get("health_score"),
        "momentum": (pulse or {}).get("engagement_momentum"),
        "audience": {
            "member_count": int(audience_row.member_count) if audience_row else None,
            "delta_7d": int(audience_row.delta_7d) if audience_row else None,
        },
        "top_topics": topic_matrix.get("top_topics") or [],
        "sources_promoted": curation.get("promoted") or [],
        "recommendations": recommendations,
    }
