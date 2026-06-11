"""Dynamic cadence unlock — engagement-aware pacing toward 18–25 posts/day (D30)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CadenceDecision:
    allowed: bool
    reason: str
    daily_cap: int
    session_cap: int
    min_interval_sec: int


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "dynamic_cadence_state.json"


def _load_state(runtime_dir: str) -> dict:
    p = _state_path(runtime_dir)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(runtime_dir: str, state: dict) -> None:
    p = _state_path(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")


def _target_daily_cap() -> int:
    try:
        phase = os.getenv("GROWTH_PHASE", "d30").strip().lower()
        if phase in {"d7", "d14"}:
            return max(18, min(50, int(os.getenv("GROWTH_CADENCE_DAILY_CAP", "35"))))
        if phase == "d90":
            return max(20, min(60, int(os.getenv("GROWTH_CADENCE_DAILY_CAP", "40"))))
        return max(12, min(30, int(os.getenv("GROWTH_CADENCE_DAILY_CAP", "20"))))
    except ValueError:
        return 20


def _engagement_boost(runtime_dir: str) -> float:
    """0..0.35 boost from cached analytics aggregate (written by poll job)."""
    p = Path(runtime_dir) / "analytics_engagement_avg.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        avg = float(data.get("avg_engagement_score") or 0.0)
        return min(0.35, avg * 0.4)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0.0


def evaluate_dynamic_cadence(
    *,
    runtime_dir: str,
    newsroom_tz: str = "Europe/Moscow",
    is_breaking: bool = False,
    topic_bucket: str = "general",
    now: datetime | None = None,
    autonomous_relaxed: bool = False,
) -> CadenceDecision:
    """
    Pseudocode:
      cap = base_cap + engagement_boost - fatigue_penalty
      if breaking: bypass interval, still respect daily_cap * 1.2
      if topic_overrepresented today: session_cap -= 1
    """
    if is_breaking:
        return CadenceDecision(True, "breaking_exempt", _target_daily_cap() + 4, 99, 30)

    tz = ZoneInfo(newsroom_tz)
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    day_key = now_local.strftime("%Y-%m-%d")
    state = _load_state(runtime_dir)
    day = state.setdefault("days", {}).setdefault(day_key, {"count": 0, "topics": {}, "hours": {}})
    count = int(day.get("count") or 0)
    topics: dict[str, int] = day.get("topics") or {}
    topic_count = int(topics.get(topic_bucket, 0))

    base_cap = _target_daily_cap()
    cap = base_cap + int(_engagement_boost(runtime_dir) * 10)
    fatigue = max(0, count - base_cap) * 2
    min_interval = max(60, int(os.getenv("PUBLISH_CHANNEL_MIN_INTERVAL_SEC", "120")) - int(_engagement_boost(runtime_dir) * 60))
    min_interval = max(45, min_interval - fatigue * 5)

    if count >= cap:
        return CadenceDecision(False, "daily_cap", cap, 0, min_interval)

    hour = now_local.hour
    from app.editorial.growth_profile import aggressive_growth_enabled
    from app.editorial.news_channel_beat import news_channel_beat_enabled

    if news_channel_beat_enabled():
        session_cap = 10 if 7 <= hour < 23 else 4
    elif aggressive_growth_enabled():
        session_cap = 8 if 7 <= hour < 23 else 3
    elif autonomous_relaxed:
        session_cap = 6 if 8 <= hour < 22 else 2
    else:
        session_cap = 3 if 8 <= hour < 22 else 1
    if topic_count >= max(2, cap // 4):
        session_cap = max(1, session_cap - 1)

    hour_count = int((day.get("hours") or {}).get(str(hour), 0))
    if hour_count >= session_cap:
        return CadenceDecision(False, "session_cap", cap, session_cap, min_interval)

    return CadenceDecision(True, "ok", cap, session_cap, min_interval)


def record_publish_for_cadence(
    *,
    runtime_dir: str,
    topic_bucket: str = "general",
    newsroom_tz: str = "Europe/Moscow",
    now: datetime | None = None,
) -> None:
    tz = ZoneInfo(newsroom_tz)
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    day_key = now_local.strftime("%Y-%m-%d")
    state = _load_state(runtime_dir)
    day = state.setdefault("days", {}).setdefault(day_key, {"count": 0, "topics": {}, "hours": {}})
    day["count"] = int(day.get("count") or 0) + 1
    topics: dict[str, int] = day.get("topics") or {}
    topics[topic_bucket] = int(topics.get(topic_bucket, 0)) + 1
    day["topics"] = topics
    hours: dict[str, int] = day.get("hours") or {}
    hours[str(now_local.hour)] = int(hours.get(str(now_local.hour), 0)) + 1
    day["hours"] = hours
    # prune old days
    keys = sorted((state.get("days") or {}).keys())
    for k in keys[:-14]:
        state["days"].pop(k, None)
    _save_state(runtime_dir, state)
