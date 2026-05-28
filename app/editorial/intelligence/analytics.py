"""Operator-facing editorial analytics (read-only)."""

from __future__ import annotations

import time
from typing import Any

from app.editorial.intelligence.memory import memory_snapshot
from app.editorial.intelligence.sandbox import active_experiments


def editorial_analytics_snapshot(runtime_dir: str) -> dict[str, Any]:
    mem = memory_snapshot(runtime_dir)
    topics = dict(mem.get("topics") or {})
    recent = list(mem.get("recent") or [])
    top_topics = sorted(
        topics.items(),
        key=lambda x: int(x[1].get("publish_count") or 0),
        reverse=True,
    )[:12]
    now = time.time()
    last_24h = [r for r in recent if isinstance(r, dict) and float(r.get("unix") or 0) >= now - 86400]
    fatigue_hotspots = [
        {"topic_key": k, "publish_count": int(v.get("publish_count") or 0)}
        for k, v in top_topics
        if int(v.get("publish_count") or 0) >= 3
    ]
    try:
        from utils.source_reputation import export_channel_scores_for_priority

        rep = export_channel_scores_for_priority(runtime_dir)
        top_sources = sorted(rep.items(), key=lambda x: -float(x[1].get("score") or 0))[:10]
    except Exception:
        top_sources = []

    return {
        "schema_version": 1,
        "generated_at_unix": now,
        "publishes_24h": len(last_24h),
        "top_topics": [{"key": k, **v} for k, v in top_topics],
        "fatigue_hotspots": fatigue_hotspots,
        "top_sources": [{"channel": k, **v} for k, v in top_sources],
        "active_experiments": active_experiments(),
        "recent_count": len(recent),
    }
