"""Bridge engagement feedback cache into channel product decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_feedback_weights(runtime_dir: str | None) -> dict[str, Any]:
    if not runtime_dir:
        return {}
    cache = Path(runtime_dir) / "engagement_feedback_cache.json"
    if not cache.is_file():
        return {}
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def topic_weights_from_feedback(runtime_dir: str | None) -> dict[str, float]:
    cached = load_feedback_weights(runtime_dir)
    tw = cached.get("topic_weights")
    if isinstance(tw, dict):
        return {str(k): float(v) for k, v in tw.items()}
    return {}


def global_momentum(runtime_dir: str | None) -> float:
    cached = load_feedback_weights(runtime_dir)
    try:
        return float(cached.get("momentum") or 0.0)
    except (TypeError, ValueError):
        return 0.0
