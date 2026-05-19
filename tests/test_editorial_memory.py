from __future__ import annotations

from pathlib import Path

from bot.editorial.memory.analyzer import analyze_editorial_memory
from bot.editorial.memory.contradiction import detect_contradictions, detect_tone_direction
from bot.editorial.memory.follow_up import classify_follow_up
from bot.editorial.memory.repository import EditorialMemoryRepository
from bot.editorial.memory.service import record_storyline_event_sync
from bot.editorial.memory.topics import extract_topic_keys, storyline_id_from_slug
from bot.editorial.memory.types import StorylineSnapshot
from bot.storage.db import init_database


def _storyline(
    *,
    sid: str,
    headline: str,
    summary: str,
    tags: tuple[str, ...] = ("inflation", "economy"),
    count: int = 2,
) -> StorylineSnapshot:
    return StorylineSnapshot(
        storyline_id=sid,
        slug="inflation-fed",
        title="Inflation / Fed policy",
        topic_keys=("inflation-fed",),
        entity_keys=("Federal Reserve",),
        first_seen_at="2026-01-01T00:00:00+00:00",
        last_updated_at="2026-01-10T12:00:00+00:00",
        publish_count=count,
        sources=("ap",),
        latest_headline=headline,
        latest_summary=summary,
        tone_direction="easing",
        saturation_score=0.2,
    )


def test_topic_extraction() -> None:
    keys = extract_topic_keys(
        "Fed holds rates as inflation cools",
        "CPI data showed softer price growth.",
        tags=["economy"],
    )
    assert "inflation-fed" in keys
    assert storyline_id_from_slug("inflation-fed") == "sl-inflation-fed"


def test_contradiction_detection() -> None:
    flags = detect_contradictions(
        prior_text="Inflation continues to ease gradually",
        prior_tone="easing",
        new_text="Inflation accelerates as prices surge",
    )
    assert flags
    assert detect_tone_direction("Markets rally after gains") == "rally"


def test_follow_up_duplicate() -> None:
    sl = _storyline(
        sid="sl-inflation-fed",
        headline="Inflation cools for third straight month",
        summary="Consumer prices rose modestly.",
    )
    kind = classify_follow_up(
        match_score=0.9,
        storyline=sl,
        headline="Inflation cools for third straight month",
        summary="Consumer prices rose modestly in March.",
    )
    assert kind == "duplicate"


def test_analyzer_warnings_saturation(tmp_path: Path) -> None:
    db = init_database(tmp_path / "mem.db")
    repo = EditorialMemoryRepository(db)
    sl = _storyline(
        sid="sl-inflation-fed",
        headline="Inflation slows again",
        summary="CPI eased.",
        count=5,
    )
    repo.upsert_storyline(
        storyline_id=sl.storyline_id,
        slug=sl.slug,
        title=sl.title,
        topic_keys=list(sl.topic_keys),
        entity_keys=list(sl.entity_keys),
        headline=sl.latest_headline or "",
        summary=sl.latest_summary,
        source="ap",
        tone_direction="easing",
        saturation_score=0.7,
        is_new=False,
    )
    for i in range(4):
        repo.record_event(
            storyline_id=sl.storyline_id,
            pending_news_id=100 + i,
            event_type="publish",
            follow_up_kind="follow_up",
            headline=f"Inflation update {i}",
            summary="CPI data.",
            source="ap",
            tags=["inflation"],
            context_snippet=None,
            contradiction_flags=[],
            novelty_score=0.5,
        )

    report = analyze_editorial_memory(
        headline="Inflation slows again in latest CPI",
        summary="Prices rose modestly.",
        tags=["inflation", "economy"],
        source="ap",
        repo=repo,
    )
    assert report.storyline_id
    assert report.follow_up_kind in ("follow_up", "minor_variation", "duplicate")
    assert any("saturation" in w for w in report.warnings) or report.saturation_score >= 0.5


def test_record_persists_events(tmp_path: Path) -> None:
    db = init_database(tmp_path / "mem2.db")
    report = record_storyline_event_sync(
        pending_news_id=42,
        headline="Nvidia shares jump on AI chip demand",
        summary="The company raised guidance for data-center revenue.",
        tags=["nvidia", "tech", "ai"],
        source="reuters",
        db_path=db,
    )
    assert report is not None
    repo = EditorialMemoryRepository(db)
    payload = repo.storyline_timeline_payload(report.storyline_id or "")
    assert payload is not None
    assert payload["publish_count"] >= 1
    assert len(payload["events"]) >= 1
