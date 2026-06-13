"""Top news-channel beat — latency + frequency preset (cb_economics-class macro wire).

Demand model (RU macro Telegram, 2024–2026):
- Readers choose one *primary* wire; switching cost is high when latency or coverage lags peers.
- Winning channels: 15–35 posts/active day, <15 min source→channel for routine, <5 min for breaking,
  zero visible human moderation queue, consistent brief format.
- This preset aligns pipeline cadence, publish spacing, governance cooldowns, and autonomy with that bar.
"""

from __future__ import annotations

import os


def news_channel_beat_enabled() -> bool:
    raw = os.getenv("NEWSROOM_CHANNEL_BEAT", "").strip().lower()
    if raw in {"1", "true", "yes", "on", "top_news", "news_beat", "wire"}:
        return True
    if raw in {"off", "false", "0", "standard", "default"}:
        return False
    if not raw:
        return os.getenv("NEWSROOM_GROWTH_MODE", "").strip().lower() in {
            "aggressive",
            "fast",
            "d7",
            "max",
            "news_beat",
        }
    return False


def news_beat_topic_cooldown_sec(*, default: float = 1800.0) -> float:
    if not news_channel_beat_enabled():
        return default
    raw = os.getenv("NEWS_BEAT_TOPIC_COOLDOWN_SEC", "600").strip()
    try:
        return max(120.0, min(3600.0, float(raw)))
    except ValueError:
        return 600.0


def apply_news_channel_beat_defaults() -> None:
    """Set env defaults when unset — explicit .env always wins."""
    if not news_channel_beat_enabled():
        return

    defaults: dict[str, str] = {
        # Reference editorial lane (@cb_economics peers)
        "NEWSROOM_REFERENCE_MODEL": "cb_economics",
        "NEWSROOM_GROWTH_MODE": "aggressive",
        "PUBLISH_OUTPUT_LANGUAGE": "ru",
        "SUMMARY_STYLE": "cb-economics-brief",
        # Full autonomy — no human moderation queue
        "AUTONOMOUS_EDITORIAL_MODE": "true",
        "LIVE_SUPERVISED_APPROVAL": "false",
        "AI_EDITORIAL_REVIEW_ENABLED": "true",
        "EDITORIAL_ZERO_HUMAN_IN_LOOP": "true",
        # Ingest + pipeline latency
        "PIPELINE_INTERVAL_MINUTES": "3",
        "BREAKING_LANE_INTERVAL_MIN": "1",
        "MIN_RAW_POSTS_FOR_AI": "1",
        "COLLECT_MESSAGES_PER_CHANNEL": "35",
        "COLLECT_PARALLEL_ENABLED": "true",
        "COLLECTOR_MEDIA_SKIP_CHANNELS": "cb_economics,tnews365",
        "FAST_LANE_ENABLED": "true",
        "CHANNEL_COLLECT_DELAY_SECONDS": "0.45",
        # Wire-speed publish path
        "WIRE_FAST_PUBLISH_ENABLED": "true",
        "WIRE_FAST_PUBLISH_SKIP_AI_REVIEW": "true",
        "WIRE_FRESHNESS_PRIORITY": "true",
        "WIRE_FRESHNESS_MAX_MIN": "20",
        "WIRE_LANE_ROUTINE_ENABLED": "true",
        "WIRE_LANE_ROUTINE_COOLDOWN_SEC": "180",
        "PUBLISH_DUE_DRAFTS_PER_TICK": "6",
        "AUTO_PUBLISH_MAX_SCHEDULE_CAP": "8",
        # Publish throughput (cb-style: several posts/hour in active sessions)
        "PUBLISH_CHANNEL_MIN_INTERVAL_SEC": "35",
        "PUBLISH_BURST_WINDOW_SEC": "600",
        "PUBLISH_BURST_MAX_MESSAGES": "8",
        "AUTO_PUBLISH_MAX_SCHEDULE_PER_TICK": "6",
        "OPS_PUBLISH_RATE_LIMIT_PER_MIN": "18",
        # Silence recovery — never feel «канал умер»
        "PUBLISH_FLOOR_MAX_SILENCE_MIN": "22",
        "EDITORIAL_ANTI_PAUSE_GAP_MINUTES": "50",
        "EDITORIAL_ANTI_PAUSE_MAX_GAP_MINUTES": "70",
        "EDITORIAL_TARGET_POSTS_PER_DAY": "28",
        "EDITORIAL_BASELINE_POSTS_PER_DAY": "14",
        # Growth cadence — high volume without timing optimizer stalls
        "GROWTH_CADENCE_DAILY_CAP": "42",
        "GROWTH_TIMING_OPTIMIZER_ENABLED": "false",
        "GROWTH_TOPIC_SATURATION_LIMIT": "0.88",
        "SOURCE_COOLDOWN_MINUTES": "4",
        "NEWS_BEAT_TOPIC_COOLDOWN_SEC": "600",
        # Editorial layers — publish-first under autonomy
        "UEOS_PUBLISH_THRESHOLD": "68",
        "UEOS_DIGEST_THRESHOLD": "52",
        "EGDL_REQUIRE_MULTI_SOURCE_CLASS": "false",
        "EDITORIAL_INFORMATIVE_MIN_CHARS_ANTI_PAUSE": "40",
        "EDITORIAL_INFORMATIVE_MIN_SENTENCES_ANTI_PAUSE": "1",
        "EAA_MIN_AUTONOMY_CONFIDENCE": "0.58",
        "NEWSROOM_CLEAN_CHANNEL_COPY": "true",
        "NEWSROOM_CB_BRIEF_FORMAT": "true",
        "NEWSROOM_PUBLISH_FORMAT": "format_ab",
        "FORMAT_AB_EXPERIMENT_ENABLED": "true",
        "FORMAT_AB_WIRE_SHARE": "0.5",
        "FORMAT_AB_MIN_COHORT": "15",
        "FORMAT_AB_MIN_TOTAL": "30",
        "NEWSROOM_HASHTAGS_ENABLED": "false",
        "PUBLIC_WHY_IT_MATTERS": "false",
        "NEWSROOM_ENGAGEMENT_HOOK_ENABLED": "false",
        "NEWSROOM_OPEN_LOOP_ENABLED": "false",
        "NEWSROOM_BRAND_FOOTER_ENABLED": "false",
        "CHANNEL_PRODUCT_SHARE_NUDGE": "true",
        "CHANNEL_PRODUCT_OPEN_LOOP": "false",
        "GROWTH_SIGNATURE_ENABLED": "false",
        "AUTONOMOUS_GROWTH_ROBOT_ENABLED": "true",
        "AUTONOMOUS_GROWTH_TUNING_ENABLED": "true",
        "GROWTH_SOURCE_YIELD_ENABLED": "true",
        "GROWTH_FEEDBACK_ENABLED": "true",
        "GROWTH_TOPIC_BOOST_ENABLED": "true",
        "GROWTH_PEAK_HOUR_MODE": "off",
        "GROWTH_PEAK_HOUR_START": "10",
        "GROWTH_PEAK_HOUR_END": "18",
        "AUTONOMOUS_SOURCE_CURATION_ENABLED": "true",
        "AUTONOMOUS_WEEKLY_REPORT_ENABLED": "true",
        "AUTONOMOUS_ACQUISITION_LOOP_ENABLED": "true",
        "NEWSROOM_REFERENCE_MODEL": "cb_economics",
    }

    for key, val in defaults.items():
        if not os.getenv(key, "").strip():
            os.environ[key] = val
