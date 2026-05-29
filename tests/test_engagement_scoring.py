"""Engagement scoring unit tests."""

from __future__ import annotations

from app.analytics.engagement_scoring import engagement_score, virality_score


def test_engagement_score_increases_with_forwards() -> None:
    low = engagement_score(views=1000, forwards=2, reactions=5, subscribers=5000, hours_since_publish=2)
    high = engagement_score(views=1000, forwards=40, reactions=5, subscribers=5000, hours_since_publish=2)
    assert high > low


def test_virality_above_baseline() -> None:
    v = virality_score(views=2000, forwards=80, subscribers=5000, channel_median_forward_rate=0.02)
    assert v > 0.5
