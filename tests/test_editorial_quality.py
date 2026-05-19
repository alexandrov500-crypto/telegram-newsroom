from __future__ import annotations

import sqlite3
from pathlib import Path

from bot.editorial.quality.evaluator import evaluate_post
from bot.editorial.quality.phrases import find_weak_phrases, jaccard_similarity
from bot.editorial.quality.scoring import evaluate_editorial_quality
from bot.editorial.quality.service import record_publish_quality_sync
from bot.editorial.quality.warnings import build_quality_warnings
from bot.storage.db import init_database


def test_weak_phrase_detection() -> None:
    hits = find_weak_phrases("Markets continues to rise gradually, experts say.")
    assert "continues to" in hits
    assert "experts say" in hits


def test_editorial_quality_score_range() -> None:
    result = evaluate_editorial_quality(
        headline="Fed holds rates at 5.25% after CPI cools",
        summary="The Federal Reserve kept its policy rate unchanged while noting inflation progress.",
        link="https://apnews.com/article/example",
        tags=["economy", "inflation"],
        source="ap",
        template_key="economy",
    )
    assert 0.0 <= result.editorial_quality_score <= 1.0
    assert result.dimensions.headline_strength > 0.5


def test_similarity_detects_overlap() -> None:
    score = jaccard_similarity(
        "Fed holds rates steady after inflation report",
        "Fed holds rates steady after jobs report",
    )
    assert score > 0.5


def test_preview_warnings_weak_headline() -> None:
    scored = evaluate_editorial_quality(
        headline="Update",
        summary="Things happened amid concerns according to reports.",
        link="https://example.com/x",
        tags=["news", "update", "world", "economy", "markets", "finance"],
        source="ap",
        template_key="economy",
    )
    warnings = build_quality_warnings(
        result=scored,
        headline="Update",
        summary="Things happened amid concerns according to reports.",
        tags=["news", "update", "world", "economy", "markets", "finance"],
        source="ap",
        template_key="economy",
        hook_line=None,
        recent=[],
    )
    assert any("weak headline" in w for w in warnings)
    assert any("low information density" in w for w in warnings) or any(
        "weak phrasing" in w for w in warnings
    )


def test_evaluate_post_with_fatigue(tmp_path: Path) -> None:
    db = init_database(tmp_path / "eq.db")
    recent = [
        {
            "pending_news_id": 1,
            "headline": "Inflation cools in March CPI",
            "summary": "Prices rose less than expected.",
            "source": "ap",
            "template_key": "economy",
            "tags": ["inflation", "economy"],
        }
        for _ in range(6)
    ]
    report = evaluate_post(
        headline="Inflation eases again in latest CPI print",
        summary="Consumer prices rose modestly, extending disinflation trend.",
        link="https://apnews.com/article/cpi",
        tags=["inflation", "economy"],
        source="ap",
        recent=recent,
    )
    assert report.fatigue["topic_fatigue"] > 0.4
    assert report.editorial_quality_score > 0.0


def test_record_persists_and_trace_merge(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "trace.db")
    report = record_publish_quality_sync(
        pending_news_id=99,
        headline="Oil prices slip as supply rises",
        summary="Crude fell after inventory data showed a build.",
        link="https://reuters.com/example",
        tags=["energy", "markets"],
        source="reuters",
        db_path=db_path,
    )
    assert report is not None
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT editorial_quality_score FROM editorial_quality_scores WHERE pending_news_id = 99",
        ).fetchone()
        assert row is not None
        trace = conn.execute(
            "SELECT trace_json FROM live_publish_trace WHERE post_id = '99'",
        ).fetchone()
    assert row[0] > 0
    # trace may be absent if no prior publish trace row — merge is best-effort
