"""Growth pulse — single snapshot for autonomous audience robot."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from db.models import ChannelAudienceSnapshot, Draft, DraftStatus, PublishedPost, SourceRegistryEntry
from db.session import session_scope


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_engagement_cache(runtime_dir: str) -> dict[str, Any]:
    path = Path(runtime_dir) / "engagement_feedback_cache.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _top_reject_reasons(rejected_extras: list[str], *, limit: int = 5) -> list[dict[str, Any]]:
    reasons: Counter[str] = Counter()
    for raw in rejected_extras:
        try:
            data = json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        for key in ("reject_reason", "desk_reject", "dominance_reject", "gate_reason"):
            val = str(data.get(key) or "").strip()
            if val:
                reasons[val] += 1
        growth = data.get("growth")
        if isinstance(growth, dict):
            val = str(growth.get("reject_reason") or growth.get("dominance_reject") or "").strip()
            if val:
                reasons[val] += 1
        stab = data.get("stability")
        if isinstance(stab, dict):
            val = str(stab.get("reject_reason") or "").strip()
            if val:
                reasons[val] += 1
    return [{"reason": r, "count": c} for r, c in reasons.most_common(limit)]


async def collect_growth_pulse(
    *,
    runtime_dir: str,
    channel_id: int | None = None,
    target_posts_per_day: float | None = None,
) -> dict[str, Any]:
    """Audience robot dashboard: throughput, silence, quality, growth signals."""
    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    target = target_posts_per_day if target_posts_per_day is not None else _env_float("EDITORIAL_TARGET_POSTS_PER_DAY", 28)

    pulse: dict[str, Any] = {
        "ts": now.isoformat(),
        "target_posts_per_day": target,
        "health": "unknown",
        "recommendations": [],
    }

    async with session_scope() as session:
        pub_24h = int(
            (
                await session.execute(
                    select(func.count(PublishedPost.id)).where(PublishedPost.published_at >= cutoff_24h)
                )
            ).scalar()
            or 0
        )
        pub_7d = int(
            (
                await session.execute(
                    select(func.count(PublishedPost.id)).where(PublishedPost.published_at >= cutoff_7d)
                )
            ).scalar()
            or 0
        )
        last_pub = (
            await session.execute(select(PublishedPost.published_at).order_by(PublishedPost.id.desc()).limit(1))
        ).scalar_one_or_none()

        rejected_rows = list(
            (
                await session.execute(
                    select(Draft.draft_extras).where(
                        Draft.created_at >= cutoff_24h,
                        Draft.status.in_((DraftStatus.REJECTED.value, DraftStatus.FAILED.value)),
                    )
                )
            ).scalars().all()
        )
        created_24h = int(
            (
                await session.execute(select(func.count(Draft.id)).where(Draft.created_at >= cutoff_24h))
            ).scalar()
            or 0
        )

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

        sources = list((await session.execute(select(SourceRegistryEntry))).scalars().all())

    silence_min = None
    if last_pub is not None:
        lp = last_pub if last_pub.tzinfo else last_pub.replace(tzinfo=UTC)
        silence_min = round(max(0.0, (now - lp).total_seconds() / 60.0), 1)

    reject_n = len(rejected_rows)
    reject_ratio = round(reject_n / max(1, created_24h), 3)
    posts_per_day_7d = round(pub_7d / 7.0, 2)

    eng = _load_engagement_cache(runtime_dir)
    momentum = float(eng.get("momentum") or 0.0)
    global_eng = float(eng.get("global_engagement") or 0.0)

    source_rank: list[dict[str, Any]] = []
    for row in sources:
        try:
            ex = json.loads(row.extras_json or "{}")
        except (json.JSONDecodeError, TypeError):
            ex = {}
        y = float(ex.get("yield_score") or 0.0)
        if y <= 0 and row.status == "active":
            continue
        source_rank.append(
            {
                "handle": row.handle,
                "tier": row.tier,
                "status": row.status,
                "yield_score": round(y, 3),
                "yield_posts": int(ex.get("yield_posts") or 0),
            }
        )
    source_rank.sort(key=lambda x: x["yield_score"], reverse=True)

    top_rejects = _top_reject_reasons(rejected_rows)

    # Health score 0–100 for operator glance
    score = 70.0
    if silence_min is not None:
        if silence_min > 120:
            score -= 25
        elif silence_min > 60:
            score -= 12
    if pub_24h < target * 0.5:
        score -= 15
    elif pub_24h >= target * 0.85:
        score += 8
    if reject_ratio > 0.5:
        score -= 15
    elif reject_ratio < 0.25:
        score += 5
    if momentum >= 0.45:
        score += 8
    score = round(max(0.0, min(100.0, score)), 1)

    if silence_min and silence_min > 70:
        pulse["recommendations"].append("silence_high: boost throughput (anti-pause / lower gate)")
    if pub_24h < target * 0.6:
        pulse["recommendations"].append("throughput_low: increase cadence or relax publish threshold")
    if reject_ratio > 0.45:
        top = top_rejects[0]["reason"] if top_rejects else "unknown"
        pulse["recommendations"].append(f"reject_high:{top}")
    if momentum < 0.35 and pub_24h >= target * 0.7:
        pulse["recommendations"].append("engagement_low: prioritize high-yield sources and forward stories")

    if score >= 75:
        health = "strong"
    elif score >= 55:
        health = "ok"
    elif score >= 40:
        health = "strained"
    else:
        health = "critical"

    pulse.update(
        {
            "health": health,
            "health_score": score,
            "published_24h": pub_24h,
            "published_7d_avg_per_day": posts_per_day_7d,
            "silence_minutes": silence_min,
            "drafts_created_24h": created_24h,
            "reject_ratio_24h": reject_ratio,
            "top_reject_reasons": top_rejects,
            "engagement_momentum": round(momentum, 3),
            "global_engagement": round(global_eng, 3),
            "audience": {
                "member_count": int(audience_row.member_count) if audience_row else None,
                "delta_24h": int(audience_row.delta_24h) if audience_row else None,
                "delta_7d": int(audience_row.delta_7d) if audience_row else None,
            },
            "sources_top": source_rank[:3],
            "sources_bottom": list(reversed(source_rank[-3:])) if source_rank else [],
        }
    )
    return pulse


def format_pulse_telegram(pulse: dict[str, Any]) -> str:
    """Compact operator message."""
    hs = pulse.get("health_score")
    icon = {"strong": "🟢", "ok": "🟡", "strained": "🟠", "critical": "🔴"}.get(
        str(pulse.get("health") or ""), "⚪"
    )
    lines = [
        f"{icon} Growth Pulse · score {hs}",
        f"📰 {pulse.get('published_24h')}/{int(pulse.get('target_posts_per_day') or 0)} posts/24h "
        f"(avg {pulse.get('published_7d_avg_per_day')}/d)",
    ]
    sm = pulse.get("silence_minutes")
    if sm is not None:
        lines.append(f"⏱ silence {sm} min")
    aud = pulse.get("audience") or {}
    if aud.get("member_count") is not None:
        lines.append(
            f"👥 subs {aud['member_count']} "
            f"(Δ24h {aud.get('delta_24h', 0):+d}, Δ7d {aud.get('delta_7d', 0):+d})"
        )
    lines.append(f"🚫 reject {float(pulse.get('reject_ratio_24h') or 0) * 100:.0f}%")
    lines.append(f"📈 momentum {pulse.get('engagement_momentum')} · eng {pulse.get('global_engagement')}")
    for rec in (pulse.get("recommendations") or [])[:2]:
        lines.append(f"→ {rec}")
    tops = pulse.get("sources_top") or []
    if tops:
        lines.append("⭐ " + ", ".join(f"@{s['handle'].lstrip('@')}" for s in tops[:2]))
    phase2 = pulse.get("phase2") or {}
    if phase2.get("peak_hour"):
        lines.append(f"🕐 peak mode: {phase2['peak_hour']}")
    top_topics = phase2.get("top_topics") or []
    if top_topics:
        lines.append("📌 " + ", ".join(str(t.get("topic")) for t in top_topics[:2]))
    return "\n".join(lines)
