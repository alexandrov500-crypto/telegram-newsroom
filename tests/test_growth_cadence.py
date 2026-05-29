from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.editorial.growth_cadence import (
    allow_story_for_current_session,
    resolve_cadence_session,
    signature_line_for_now,
)


def test_resolve_cadence_sessions_by_hour() -> None:
    tz = ZoneInfo("Europe/Moscow")
    morning = resolve_cadence_session(now_local=datetime(2026, 5, 28, 8, 30, tzinfo=tz))
    intraday = resolve_cadence_session(now_local=datetime(2026, 5, 28, 13, 0, tzinfo=tz))
    evening = resolve_cadence_session(now_local=datetime(2026, 5, 28, 20, 15, tzinfo=tz))
    assert morning.key == "morning_briefing"
    assert intraday.key == "intraday_signals"
    assert evening.key == "evening_recap"


def test_session_cap_blocks_excess_low_value_posts(tmp_path) -> None:
    tz = ZoneInfo("Europe/Moscow")
    now = datetime(2026, 5, 28, 8, 15, tzinfo=tz)
    for _ in range(2):
        allowed, reason, sess = allow_story_for_current_session(
            runtime_dir=str(tmp_path),
            priority_score=80.0,
            is_breaking=False,
            now_local=now,
        )
        assert allowed
        assert reason == "allowed"
        assert sess.key == "morning_briefing"

    allowed, reason, _ = allow_story_for_current_session(
        runtime_dir=str(tmp_path),
        priority_score=80.0,
        is_breaking=False,
        now_local=now,
    )
    assert not allowed
    assert reason == "session_cap_reached"


def test_breaking_bypasses_cadence_caps(tmp_path) -> None:
    tz = ZoneInfo("Europe/Moscow")
    now = datetime(2026, 5, 28, 2, 15, tzinfo=tz)
    allowed, reason, _ = allow_story_for_current_session(
        runtime_dir=str(tmp_path),
        priority_score=10.0,
        is_breaking=True,
        now_local=now,
    )
    assert allowed
    assert reason == "breaking_immediate"


def test_signature_line_matches_session() -> None:
    tz = ZoneInfo("Europe/Moscow")
    sig = signature_line_for_now(now_local=datetime(2026, 5, 28, 20, 0, tzinfo=tz))
    assert sig == "Closing Bell"
