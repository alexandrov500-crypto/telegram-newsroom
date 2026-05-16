"""Lightweight trend signals from topic memory (no streaming framework)."""

from __future__ import annotations

import time
from typing import Any

from editorial.topic_memory import export_topic_snapshot


def detect_topic_trends(
    runtime_dir: str | None,
    *,
    burst_count: int = 5,
    window_sec: float = 3600.0,
) -> dict[str, Any]:
    """
    Burst: topics with ``count`` high in short window approximated via last_ts recency + count.
    """
    now = time.time()
    rows = export_topic_snapshot(runtime_dir, limit=60)
    bursts: list[dict[str, Any]] = []
    for r in rows:
        c = int(r.get("count") or 0)
        last_ts = float(r.get("last_ts") or 0)
        if c < burst_count:
            continue
        if now - last_ts > window_sec * 3:
            continue
        momentum = min(1.0, c / 20.0)
        age_h = max(0.0, (now - last_ts) / 3600.0)
        bursts.append(
            {
                "hint": r.get("hint"),
                "count": c,
                "trend_momentum": round(momentum, 3),
                "trend_age_hours": round(age_h, 2),
                "trend_confidence": round(min(1.0, 0.35 + 0.05 * c), 3),
            }
        )
    bursts.sort(key=lambda x: (-int(x.get("count") or 0), x.get("trend_age_hours")))
    return {"bursts": bursts[:12], "generated_at": now}


def source_convergence_score(posts: list[Any], *, min_channels: int = 3) -> float:
    """Higher when many distinct channels cover the same story (proxy)."""
    chans = {str(getattr(p, "channel_name", "") or "").strip().lower() for p in posts}
    chans.discard("")
    n = len(chans)
    if n >= min_channels:
        return 0.85
    if n == 2:
        return 0.55
    return 0.25
