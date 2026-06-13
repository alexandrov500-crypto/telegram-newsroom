"""Topic boost matrix from engagement feedback — prioritize high-ROI themes."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.growth.engagement_feedback import load_engagement_feedback


def topic_boost_enabled() -> bool:
    return os.getenv("GROWTH_TOPIC_BOOST_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _matrix_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "topic_boost_matrix.json"


def refresh_topic_boost_matrix(runtime_dir: str) -> dict[str, Any]:
    """Build topic → multiplier from Bayesian topic weights vs global mean."""
    feedback = load_engagement_feedback(runtime_dir)
    global_mean = max(0.15, float(feedback.global_engagement or 0.35))
    boosts: dict[str, float] = {}
    for topic, weight in (feedback.topic_weights or {}).items():
        w = float(weight)
        if w >= global_mean * 1.08:
            boosts[topic] = round(min(1.35, 1.0 + (w - global_mean) * 1.2), 3)
        elif w <= global_mean * 0.82:
            boosts[topic] = round(max(0.75, 1.0 - (global_mean - w) * 0.8), 3)

    top_topics = sorted(
        feedback.topic_weights.items(),
        key=lambda kv: float(kv[1]),
        reverse=True,
    )[:5]

    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "global_engagement": global_mean,
        "boosts": boosts,
        "top_topics": [{"topic": t, "weight": round(float(w), 4)} for t, w in top_topics],
    }
    path = _matrix_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def load_topic_boost_matrix(runtime_dir: str) -> dict[str, Any]:
    if not topic_boost_enabled():
        return {}
    try:
        data = json.loads(_matrix_path(runtime_dir).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def topic_boost_multiplier(topic_bucket: str, runtime_dir: str) -> float:
    if not topic_boost_enabled():
        return 1.0
    matrix = load_topic_boost_matrix(runtime_dir)
    boosts = matrix.get("boosts") if isinstance(matrix.get("boosts"), dict) else {}
    tb = (topic_bucket or "general").strip().lower()
    if tb in boosts:
        return float(boosts[tb])
    root = tb.split("_")[0]
    return float(boosts.get(root, 1.0))
