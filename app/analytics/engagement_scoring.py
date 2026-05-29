"""Engagement and virality scoring from measured Telegram post metrics."""

from __future__ import annotations

import math
from typing import Any


def engagement_score(
    *,
    views: int = 0,
    forwards: int = 0,
    reactions: int = 0,
    subscribers: int = 0,
    hours_since_publish: float = 1.0,
) -> float:
    """
    Normalized engagement 0..1.

    forward_rate and reaction_rate dominate; views provide reach context.
    """
    subs = max(subscribers, 1)
    hrs = max(hours_since_publish, 0.25)
    view_rate = min(1.0, views / subs)
    forward_rate = min(1.0, (forwards / max(views, 1)) * 25.0)
    reaction_rate = min(1.0, (reactions / max(views, 1)) * 40.0)
    velocity = min(1.0, views / (subs * hrs * 0.15))
    raw = 0.35 * forward_rate + 0.25 * reaction_rate + 0.25 * view_rate + 0.15 * velocity
    return round(max(0.0, min(1.0, raw)), 4)


def virality_score(
    *,
    views: int = 0,
    forwards: int = 0,
    subscribers: int = 0,
    channel_median_forward_rate: float = 0.02,
) -> float:
    """Shareability proxy: forwards vs channel baseline."""
    if views <= 0:
        return 0.0
    fr = forwards / views
    baseline = max(channel_median_forward_rate, 0.005)
    ratio = fr / baseline
    return round(max(0.0, min(1.0, 1.0 - math.exp(-ratio))), 4)


def metrics_to_trend_memory_payload(row: dict[str, Any]) -> dict[str, float]:
    """Map DB metrics row → trend_memory.observe_narrative_event kwargs."""
    views = int(row.get("views") or 0)
    forwards = int(row.get("forwards") or 0)
    reactions = int(row.get("reactions_total") or 0)
    subs = int(row.get("subscribers_at_snapshot") or 0)
    hrs = float(row.get("hours_since_publish") or 1.0)
    eng = engagement_score(
        views=views,
        forwards=forwards,
        reactions=reactions,
        subscribers=subs,
        hours_since_publish=hrs,
    )
    vir = virality_score(views=views, forwards=forwards, subscribers=subs)
    return {
        "repost_rate": vir,
        "forward_velocity": min(1.0, forwards / max(subs, 1) * 50.0),
        "open_retention": min(1.0, views / max(subs, 1)),
        "reaction_density": min(1.0, reactions / max(views, 1) * 30.0),
        "quoteability": eng * 0.85,
        "screenshot_probability": eng * 0.6,
        "engagement_longevity": min(1.0, eng * (1.0 + hrs / 48.0) / 2.0),
    }
