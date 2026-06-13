"""Phase 2 autonomous growth robot tests."""

from __future__ import annotations

import json

import pytest

from app.growth.autonomous_robot.peak_hours import evaluate_peak_hour
from app.growth.autonomous_robot.topic_boost import refresh_topic_boost_matrix, topic_boost_multiplier
from app.growth.autonomous_robot.weekly_report import format_weekly_growth_report


def test_peak_hour_soft_in_window() -> None:
    v = evaluate_peak_hour(hour_local=12, is_breaking=False)
    assert v.in_peak
    assert v.score_multiplier > 1.0
    assert not v.defer


def test_peak_hour_breaking_never_deferred() -> None:
    v = evaluate_peak_hour(hour_local=3, is_breaking=True)
    assert not v.defer


def test_peak_hour_off_peak_soft() -> None:
    v = evaluate_peak_hour(hour_local=22, is_breaking=False)
    assert not v.in_peak
    assert v.score_multiplier < 1.0
    assert not v.defer


def test_topic_boost_matrix(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_TOPIC_BOOST_ENABLED", "true")
    runtime = str(tmp_path)
    cache = tmp_path / "engagement_feedback_cache.json"
    cache.write_text(
        json.dumps(
            {
                "topic_weights": {"macro": 0.62, "crypto": 0.18},
                "global_engagement": 0.35,
            }
        ),
        encoding="utf-8",
    )
    matrix = refresh_topic_boost_matrix(runtime)
    assert matrix.get("top_topics")
    assert topic_boost_multiplier("macro", runtime) > 1.0
    assert topic_boost_multiplier("crypto", runtime) < 1.0


def test_weekly_report_format() -> None:
    text = format_weekly_growth_report(
        {
            "published_7d": 140,
            "avg_per_day": 20,
            "avg_engagement": 0.41,
            "health_score": 72,
            "momentum": 0.05,
            "audience": {"member_count": 1500, "delta_7d": 42},
            "top_topics": [{"topic": "macro"}],
            "recommendations": ["keep cadence"],
        }
    )
    assert "Weekly Growth Report" in text
    assert "140" in text
