"""Tests for wire freshness scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.growth.wire_freshness import draft_age_minutes, freshness_boost, wire_freshness_max_minutes


def test_freshness_boost_decays_with_age() -> None:
    assert freshness_boost(1.0) == 1.0
    mid = freshness_boost(10.0, max_min=20.0)
    old = freshness_boost(30.0, max_min=20.0)
    assert mid > old
    assert old <= 0.15


def test_draft_age_minutes_from_created_at() -> None:
    now = datetime.now(UTC)
    draft = type("_D", (), {"created_at": now - timedelta(minutes=12)})()
    age = draft_age_minutes(draft, now=now)
    assert 11.5 <= age <= 12.5


def test_wire_freshness_max_minutes_bounded() -> None:
    assert wire_freshness_max_minutes() >= 5.0
