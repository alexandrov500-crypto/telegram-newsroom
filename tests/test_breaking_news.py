from __future__ import annotations

from ai.breaking_news import detect_breaking_news


def test_detect_breaking_multi_signal() -> None:
    out = detect_breaking_news(
        content="BREAKING: alert on markets",
        sources=[{"channel": "@a"}, {"channel": "@b"}, {"channel": "@c"}],
        duplicate_intel={"severity": "high"},
        priority={"numeric_priority_score": 0.9},
        recent_similar_count=3,
    )
    assert out["is_breaking"] is True
    assert float(out["breaking_score"]) >= 0.62


def test_detect_breaking_negative() -> None:
    out = detect_breaking_news(
        content="routine weekly summary",
        sources=[{"channel": "@a"}],
        duplicate_intel={"severity": "none"},
        priority={"numeric_priority_score": 0.2},
        recent_similar_count=0,
    )
    assert out["is_breaking"] is False
