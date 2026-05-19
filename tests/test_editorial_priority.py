from __future__ import annotations

from pathlib import Path

from bot.editorial.priority.classification import URGENCY_BREAKING, classify_urgency
from bot.editorial.priority.confirmation import cross_source_confirmation_score
from bot.editorial.priority.entities import score_entity_significance
from bot.editorial.priority.scoring import compute_editorial_priority
from bot.editorial.priority.service import build_ranked_queue
from bot.storage.db import init_database
from bot.storage.editorial_repository import PendingNewsItem


def test_entity_weighting() -> None:
    score, hits = score_entity_significance(
        "Fed holds rates steady",
        "Federal Reserve policy unchanged.",
    )
    assert score >= 0.9
    assert hits


def test_cross_source_confirmation() -> None:
    single, _ = cross_source_confirmation_score(
        source="blog",
        source_count=1,
        variant_count=1,
        sources=(),
        source_trust=0.4,
    )
    multi, _ = cross_source_confirmation_score(
        source="ap",
        source_count=3,
        variant_count=3,
        sources=("ap", "reuters", "bloomberg"),
        source_trust=0.85,
    )
    assert multi > single


def test_priority_score_high_for_major_story() -> None:
    result = compute_editorial_priority(
        headline="SEC approves spot Bitcoin ETF after years of review",
        summary="Regulators cleared the first batch of spot bitcoin funds for trading.",
        tags=["crypto", "regulation"],
        source="ap",
        source_trust=0.9,
        source_count=3,
        variant_count=3,
        sources=("ap", "reuters"),
        memory_saturation=0.1,
        memory_match_score=0.2,
        follow_up_kind="new_development",
    )
    assert result.editorial_priority_score >= 0.55
    assert result.factors.cross_source_confirmation >= 0.5


def test_low_signal_warnings() -> None:
    result = compute_editorial_priority(
        headline="Markets inch higher",
        summary="Stocks edged up slightly in quiet trade.",
        tags=["markets"],
        source="unknown",
        source_trust=0.4,
        source_count=1,
        variant_count=1,
        sources=(),
        memory_saturation=0.6,
        memory_match_score=0.9,
        follow_up_kind="duplicate",
    )
    assert result.editorial_priority_score < 0.55
    assert result.warnings


def test_urgency_breaking_classification() -> None:
    u = classify_urgency(
        editorial_priority_score=0.85,
        momentum=0.7,
        novelty=0.8,
        market_impact=0.8,
        geopolitical_impact=0.3,
        is_duplicate_follow_up=False,
    )
    assert u == URGENCY_BREAKING


def test_ranked_queue_empty_db(tmp_path: Path) -> None:
    db = init_database(tmp_path / "prio.db")
    ranked, meta = build_ranked_queue(limit=5, db_path=db)
    assert ranked == []
    assert "drift" in meta
