"""Unified growth cadence gate — wires dynamic cadence + feedback + timing."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.editorial.cadence_dynamic import evaluate_dynamic_cadence, record_publish_for_cadence
from app.growth.engagement_feedback import load_engagement_feedback
from app.growth.timing_optimizer import evaluate_publish_timing
from app.growth.topic_fatigue import evaluate_topic_fatigue


@dataclass(frozen=True)
class GrowthCadenceVerdict:
    block: bool
    reasons: list[str]
    min_interval_sec: int
    daily_cap: int
    momentum: float


def _enabled() -> bool:
    return os.getenv("GROWTH_CADENCE_ENGINE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _topic_bucket_from_key(topic_key: str, content: str) -> str:
    low = (content or topic_key or "").lower()
    for bucket in ("breaking", "crypto", "macro", "geopolitics", "finance", "energy", "corporate"):
        if bucket in low:
            return bucket
    return "general"


def evaluate_growth_cadence_gate(
    settings: Any,
    runtime_dir: str | None,
    *,
    topic_key: str,
    content: str = "",
    is_breaking: bool = False,
    narrative_id: str = "",
    now_unix: float | None = None,
) -> GrowthCadenceVerdict:
    """
    Publish arbitration layer on top of editorial.cadence burst/quiet rules.

    State machine: IDLE → MOMENTUM → SATURATED → COOLDOWN (via fatigue + caps).
    """
    if not _enabled() or not runtime_dir:
        return GrowthCadenceVerdict(False, [], 120, 20, 0.0)
    if is_breaking:
        return GrowthCadenceVerdict(False, [], 30, 24, 0.0)

    autonomous_relaxed = False
    try:
        from app.editorial.ai_editorial_reviewer import autonomous_editorial_mode_enabled

        autonomous_relaxed = autonomous_editorial_mode_enabled()
    except Exception:
        pass

    reasons: list[str] = []
    tz = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
    topic_bucket = _topic_bucket_from_key(topic_key, content)
    feedback = load_engagement_feedback(runtime_dir)

    dyn = evaluate_dynamic_cadence(
        runtime_dir=runtime_dir,
        newsroom_tz=tz,
        is_breaking=False,
        topic_bucket=topic_bucket,
        autonomous_relaxed=autonomous_relaxed,
    )
    if not dyn.allowed:
        reasons.append(f"growth_cadence_{dyn.reason}")

    fatigue = evaluate_topic_fatigue(
        runtime_dir=runtime_dir,
        topic_key=topic_key,
        content=content,
        narrative_id=narrative_id,
        is_breaking=False,
    )
    if fatigue.suppress:
        reasons.append(f"growth_fatigue_{fatigue.reason}")

    try:
        hour = datetime.fromtimestamp(float(now_unix or time.time()), tz=ZoneInfo(tz)).hour
    except Exception:
        hour = datetime.now(ZoneInfo("Europe/Moscow")).hour

    timing = evaluate_publish_timing(runtime_dir, hour_local=hour, topic_bucket=topic_bucket)
    if timing.defer and not autonomous_relaxed:
        reasons.append(f"growth_timing_{timing.reason}")

    min_interval = dyn.min_interval_sec
    try:
        from app.growth.autonomous_robot.peak_hours import evaluate_peak_hour

        peak = evaluate_peak_hour(hour_local=hour, is_breaking=is_breaking, newsroom_tz=tz)
        min_interval = max(30, int(min_interval * peak.interval_multiplier))
        if peak.defer and not autonomous_relaxed and not is_breaking:
            reasons.append(f"peak_hour_{peak.reason}")
    except Exception:
        pass

    try:
        from app.monetization.financial_feedback import load_topic_roi_weights_sync, profitability_boost

        roi_weights = load_topic_roi_weights_sync(runtime_dir)
        roi_boost = profitability_boost(topic_bucket, roi_weights)
        if roi_boost < 0.92 and not reasons:
            min_interval = int(min_interval * 1.08)
        elif roi_boost > 1.08 and not reasons:
            min_interval = max(45, int(min_interval * 0.92))
    except Exception:
        pass

    if feedback.momentum > 0.08 and not reasons:
        min_interval = max(45, int(min_interval * 0.85))
    if feedback.low_engagement_streak >= 3 and not autonomous_relaxed:
        min_interval = int(min_interval * 1.25)
        if feedback.global_engagement < 0.28:
            reasons.append("growth_low_engagement_slowdown")

    data_path = runtime_dir
    from editorial.intelligence_store import cadence_state_path, load_json

    cadence = load_json(cadence_state_path(data_path), {})
    last = float(cadence.get("last_publish_unix") or 0.0)
    now = float(now_unix or time.time())
    if min_interval > 0 and last > 0 and (now - last) < min_interval:
        reasons.append("growth_min_interval")

    return GrowthCadenceVerdict(
        block=bool(reasons),
        reasons=reasons,
        min_interval_sec=min_interval,
        daily_cap=dyn.daily_cap,
        momentum=feedback.momentum,
    )


def record_growth_cadence_publish(
    *,
    runtime_dir: str,
    topic_key: str,
    content: str,
    topic_bucket: str = "general",
    narrative_id: str = "",
    newsroom_tz: str = "Europe/Moscow",
) -> None:
    record_publish_for_cadence(
        runtime_dir=runtime_dir,
        topic_bucket=topic_bucket,
        newsroom_tz=newsroom_tz,
    )
    from app.growth.topic_fatigue import record_topic_publish
    from app.editorial.cadence_intelligence import record_cadence_intelligence

    record_topic_publish(
        runtime_dir=runtime_dir,
        topic_key=topic_key,
        content=content,
        narrative_id=narrative_id,
    )
    record_cadence_intelligence(runtime_dir, content=content, topic_key=topic_key)
