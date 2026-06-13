"""Tests for autonomous growth robot."""

from __future__ import annotations

import os

import pytest

from app.growth.autonomous_robot.controller import decide_autonomous_adjustments
from app.growth.autonomous_robot.pulse import format_pulse_telegram
from app.growth.autonomous_robot.tuning_store import apply_tuning_overrides_to_env, set_override


def test_decide_throughput_recovery_on_silence() -> None:
    pulse = {
        "target_posts_per_day": 28,
        "published_24h": 4,
        "silence_minutes": 95,
        "reject_ratio_24h": 0.2,
        "engagement_momentum": 0.4,
        "top_reject_reasons": [],
    }
    actions = decide_autonomous_adjustments(pulse)
    assert actions
    assert actions[0]["key"] == "UEOS_PUBLISH_THRESHOLD"
    assert actions[0]["value"] < float(os.getenv("UEOS_PUBLISH_THRESHOLD", "68"))


def test_decide_quality_guard_on_high_reject() -> None:
    pulse = {
        "target_posts_per_day": 28,
        "published_24h": 16,
        "silence_minutes": 20,
        "reject_ratio_24h": 0.55,
        "engagement_momentum": 0.4,
        "top_reject_reasons": [{"reason": "dominance_growth_reject", "count": 12}],
    }
    os.environ["UEOS_PUBLISH_THRESHOLD"] = "70"
    actions = decide_autonomous_adjustments(pulse)
    assert actions
    assert actions[0]["key"] == "UEOS_PUBLISH_THRESHOLD"
    assert actions[0]["value"] > 70


def test_tuning_store_applies_override(tmp_path) -> None:
    runtime = str(tmp_path)
    set_override(runtime, "UEOS_PUBLISH_THRESHOLD", 66, reason="test")
    os.environ.pop("UEOS_PUBLISH_THRESHOLD", None)
    applied = apply_tuning_overrides_to_env(runtime)
    assert applied.get("UEOS_PUBLISH_THRESHOLD") == "66"
    assert os.getenv("UEOS_PUBLISH_THRESHOLD") == "66"


def test_format_pulse_telegram() -> None:
    text = format_pulse_telegram(
        {
            "health": "ok",
            "health_score": 72,
            "published_24h": 18,
            "target_posts_per_day": 28,
            "published_7d_avg_per_day": 16,
            "silence_minutes": 42,
            "reject_ratio_24h": 0.22,
            "engagement_momentum": 0.41,
            "global_engagement": 0.38,
            "recommendations": ["throughput_low"],
            "audience": {"member_count": 1200, "delta_24h": 15, "delta_7d": 80},
            "sources_top": [{"handle": "cb_economics", "yield_score": 0.7}],
        }
    )
    assert "Growth Pulse" in text
    assert "18/28" in text
    assert "subs 1200" in text
