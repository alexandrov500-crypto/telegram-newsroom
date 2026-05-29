"""Publish-hour learning and slot competition avoidance."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.growth.engagement_feedback import load_engagement_feedback


@dataclass(frozen=True)
class TimingVerdict:
    defer: bool
    reason: str
    hour_score: float
    recommended_hour: int | None


def _heatmap_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "publish_hour_heatmap.json"


def record_publish_hour(runtime_dir: str, *, hour_local: int, engagement_score: float) -> None:
    p = _heatmap_path(runtime_dir)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"hours": {}}
    hours: dict = dict(data.get("hours") or {})
    key = str(int(hour_local) % 24)
    row = dict(hours.get(key) or {"count": 0, "eng_sum": 0.0})
    row["count"] = int(row.get("count") or 0) + 1
    row["eng_sum"] = float(row.get("eng_sum") or 0.0) + float(engagement_score or 0.0)
    hours[key] = row
    data["hours"] = hours
    data["updated_at"] = datetime.now(UTC).isoformat()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def _best_hour(feedback_hour_weights: dict[str, float]) -> int | None:
    if not feedback_hour_weights:
        return None
    return max(feedback_hour_weights.items(), key=lambda x: float(x[1]))[0]


def evaluate_publish_timing(
    runtime_dir: str,
    *,
    hour_local: int,
    topic_bucket: str = "general",
) -> TimingVerdict:
    if os.getenv("GROWTH_TIMING_OPTIMIZER_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return TimingVerdict(False, "disabled", 0.5, None)

    feedback = load_engagement_feedback(runtime_dir)
    hour_key = str(int(hour_local) % 24)
    hour_score = float(feedback.hour_weights.get(hour_key, feedback.global_engagement))

    try:
        min_score = float(os.getenv("GROWTH_MIN_HOUR_SCORE", "0.22"))
    except ValueError:
        min_score = 0.22

    best_raw = _best_hour(feedback.hour_weights)
    best_hour = int(best_raw) if best_raw is not None else None

    if hour_score < min_score and 8 <= hour_local <= 22:
        return TimingVerdict(True, "weak_hour", round(hour_score, 4), best_hour)

    return TimingVerdict(False, "ok", round(hour_score, 4), best_hour)
