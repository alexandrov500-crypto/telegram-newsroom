"""Bayesian-smoothed engagement feedback from post_performance."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from db.models import PostPerformance
from db.session import session_scope


def _enabled() -> bool:
    return os.getenv("GROWTH_FEEDBACK_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _prior_mean() -> float:
    try:
        return float(os.getenv("GROWTH_ENGAGEMENT_PRIOR_MEAN", "0.35"))
    except ValueError:
        return 0.35


def _prior_strength() -> float:
    try:
        return max(2.0, float(os.getenv("GROWTH_ENGAGEMENT_PRIOR_STRENGTH", "8")))
    except ValueError:
        return 8.0


def _cache_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "engagement_feedback_cache.json"


@dataclass(frozen=True)
class EngagementFeedback:
    topic_weights: dict[str, float]
    source_weights: dict[str, float]
    hour_weights: dict[str, float]
    vertical_weights: dict[str, float]
    global_engagement: float
    momentum: float
    low_engagement_streak: int


def _bayesian_rate(success_sum: float, count: float, *, prior_mean: float | None = None) -> float:
    p = prior_mean if prior_mean is not None else _prior_mean()
    k = _prior_strength()
    return (success_sum + k * p) / (count + k)


async def refresh_engagement_feedback(runtime_dir: str, *, window_days: int = 14) -> EngagementFeedback:
    """Aggregate post_performance → cached weights for editorial decisions."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    topic: dict[str, list[float]] = {}
    source: dict[str, list[float]] = {}
    hour: dict[str, list[float]] = {}
    vertical: dict[str, list[float]] = {}
    global_scores: list[float] = []

    if _enabled():
        async with session_scope() as session:
            q = select(PostPerformance).where(
                PostPerformance.snapshot_at >= cutoff,
                PostPerformance.snapshot_label.in_(("t1h", "t6h", "t24h")),
            )
            rows = list((await session.execute(q)).scalars().all())
            for r in rows:
                eng = float(r.engagement_score or 0.0)
                vir = float(r.virality_score or 0.0)
                score = 0.65 * eng + 0.35 * vir
                global_scores.append(score)
                tb = (r.topic_bucket or "general").strip().lower() or "general"
                topic.setdefault(tb, []).append(score)
                src = (r.primary_source or "").strip().lower().lstrip("@")
                if src:
                    source.setdefault(src, []).append(score)
                hour.setdefault(str(int(r.publish_hour_local) % 24), []).append(score)
                vertical.setdefault(tb.split("_")[0], []).append(score)

    def _weights(bucket: dict[str, list[float]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, vals in bucket.items():
            out[k] = round(_bayesian_rate(sum(vals), len(vals)), 4)
        return out

    tw = _weights(topic)
    sw = _weights(source)
    hw = _weights(hour)
    vw = _weights(vertical)
    global_eng = round(_bayesian_rate(sum(global_scores), len(global_scores)), 4) if global_scores else _prior_mean()

    cache = _cache_path(runtime_dir)
    prev: dict[str, Any] = {}
    try:
        prev = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    streak = int(prev.get("low_engagement_streak") or 0)
    if global_eng < _prior_mean() * 0.85:
        streak += 1
    else:
        streak = max(0, streak - 1)

    prev_global = float(prev.get("global_engagement") or global_eng)
    momentum = round(max(-1.0, min(1.0, global_eng - prev_global)), 4)

    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "topic_weights": tw,
        "source_weights": sw,
        "hour_weights": hw,
        "vertical_weights": vw,
        "global_engagement": global_eng,
        "momentum": momentum,
        "low_engagement_streak": streak,
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload), encoding="utf-8")

    return EngagementFeedback(
        topic_weights=tw,
        source_weights=sw,
        hour_weights=hw,
        vertical_weights=vw,
        global_engagement=global_eng,
        momentum=momentum,
        low_engagement_streak=streak,
    )


def load_engagement_feedback(runtime_dir: str) -> EngagementFeedback:
    try:
        data = json.loads(_cache_path(runtime_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return EngagementFeedback({}, {}, {}, {}, _prior_mean(), 0.0, 0)
    return EngagementFeedback(
        topic_weights=dict(data.get("topic_weights") or {}),
        source_weights=dict(data.get("source_weights") or {}),
        hour_weights=dict(data.get("hour_weights") or {}),
        vertical_weights=dict(data.get("vertical_weights") or {}),
        global_engagement=float(data.get("global_engagement") or _prior_mean()),
        momentum=float(data.get("momentum") or 0.0),
        low_engagement_streak=int(data.get("low_engagement_streak") or 0),
    )


def topic_affinity(feedback: EngagementFeedback, topic_bucket: str) -> float:
    tb = (topic_bucket or "general").strip().lower()
    return float(feedback.topic_weights.get(tb, feedback.global_engagement))


def source_affinity(feedback: EngagementFeedback, source_handle: str) -> float:
    h = (source_handle or "").strip().lower().lstrip("@")
    if not h:
        return feedback.global_engagement
    return float(feedback.source_weights.get(h, feedback.global_engagement))


def hour_affinity(feedback: EngagementFeedback, hour_local: int) -> float:
    return float(feedback.hour_weights.get(str(int(hour_local) % 24), feedback.global_engagement))


def velocity_curve(hours_since_publish: float, engagement: float) -> float:
    """Early velocity proxy — higher when engagement accumulates fast."""
    hrs = max(0.5, hours_since_publish)
    return round(min(1.0, engagement / math.sqrt(hrs)), 4)
