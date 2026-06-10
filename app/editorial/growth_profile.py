"""Growth mode presets — post chrome + publish cadence for audience acquisition."""

from __future__ import annotations

import os


def growth_mode() -> str:
    raw = os.getenv("NEWSROOM_GROWTH_MODE", "").strip().lower()
    if raw in {"", "off", "none", "false", "0", "standard", "default"}:
        return "standard"
    return raw


def aggressive_growth_enabled() -> bool:
    return growth_mode() in {"aggressive", "fast", "d7", "max"}


def apply_growth_profile_defaults() -> None:
    """
    Set growth env defaults when unset. Explicit .env always wins.
    Aggressive mode: max reach while keeping cb_economics editorial quality.
    """
    mode = growth_mode()
    if mode == "standard":
        return

    if aggressive_growth_enabled():
        defaults = {
            "GROWTH_PHASE": "d7",
            "GROWTH_CADENCE_DAILY_CAP": "35",
            "GROWTH_CADENCE_ENGINE_ENABLED": "true",
            "GROWTH_FEEDBACK_ENABLED": "true",
            "GROWTH_SOURCE_YIELD_ENABLED": "true",
            "GROWTH_TIMING_OPTIMIZER_ENABLED": "false",
            "GROWTH_TOPIC_SATURATION_LIMIT": "0.85",
            "GROWTH_EXPLORE_BUDGET_DAILY": "5",
            "PUBLISH_CHANNEL_MIN_INTERVAL_SEC": "75",
            "AUTO_PUBLISH_MAX_SCHEDULE_PER_TICK": "5",
            "AUTO_PUBLISH_BACKLOG_RELIEF_ENABLED": "true",
            "PUBLISH_FLOOR_MAX_SILENCE_MIN": "25",
            "PIPELINE_INTERVAL_MINUTES": "10",
            "RETENTION_HABIT_ENABLED": "true",
            "NEWSROOM_ENGAGEMENT_HOOK_ENABLED": "true",
            "NEWSROOM_HASHTAGS_ENABLED": "true",
            "NEWSROOM_HASHTAGS_MAX": "3",
            "NEWSROOM_OPEN_LOOP_ENABLED": "false",
            "NEWSROOM_BRAND_FOOTER_ENABLED": "true",
            "NEWSROOM_SHARE_NUDGE_ENABLED": "true",
            "GROWTH_SIGNATURE_ENABLED": "false",
            "TELEGRAM_ANALYTICS_ENABLED": "true",
        }
    else:
        defaults = {}

    for key, val in defaults.items():
        if not os.getenv(key, "").strip():
            os.environ[key] = val
