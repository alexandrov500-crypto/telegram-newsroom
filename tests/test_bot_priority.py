from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.processing import priority as pr
from bot.storage.db import init_database
from bot.storage.editorial_repository import EditorialRepository


def test_regulation_multi_source_ranks_high(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIGH_TRUST_SOURCES", "reuters,bloomberg,ap")

    async def run() -> dict:
        return await pr.calculate_priority(
            title="SEC approves new crypto ETF framework",
            summary="Regulators introduced updated ETF guidance after urgent review.",
            tags=["regulation", "crypto", "etf"],
            source_count=4,
            cluster_variants=4,
            source_name="Reuters",
        )

    result = asyncio.run(run())
    assert float(result["score"]) >= 0.75
    assert "regulation" in str(result["reason"]).lower() or "sources" in str(result["reason"]).lower()


def test_promo_story_ranks_low() -> None:
    async def run() -> dict:
        return await pr.calculate_priority(
            title="Celebrity gossip: sponsored promo deal inside",
            summary="Limited time discount advertisement for fans.",
            tags=["entertainment"],
            source_count=1,
            cluster_variants=1,
            source_name="TabloidFeed",
        )

    result = asyncio.run(run())
    assert float(result["score"]) < 0.45


def test_missing_data_fallback_safe() -> None:
    async def run() -> dict:
        return await pr.calculate_priority(
            title="",
            summary=None,
            tags=None,
            source_count=0,
            cluster_variants=0,
            source_name=None,
        )

    result = asyncio.run(run())
    assert float(result["score"]) == pytest.approx(0.5, abs=0.01)
    assert "reason" in result


def test_malformed_tags_do_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr, "_compute_priority", lambda **_: (_ for _ in ()).throw(ValueError("boom")))

    async def run() -> dict:
        return await pr.calculate_priority(
            title="Test",
            summary="Body",
            tags=["ok"],
            source_count=1,
            cluster_variants=1,
            source_name="x",
        )

    result = asyncio.run(run())
    assert float(result["score"]) == 0.5


def test_queue_sorting_by_priority(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "priority_sort.db")
    editorial = EditorialRepository(db_path)

    editorial.enqueue_news(
        title="Low noise",
        summary="Minor update",
        link="https://example.com/low",
        tags=["misc"],
        priority_score=0.25,
        priority_reason="low signal",
        source_count=1,
    )
    editorial.enqueue_news(
        title="Major regulation story",
        summary="Breaking approval",
        link="https://example.com/high",
        tags=["regulation"],
        priority_score=0.92,
        priority_reason="regulation + 3 sources",
        source_count=3,
    )
    editorial.enqueue_news(
        title="Medium item",
        summary="Update",
        link="https://example.com/mid",
        tags=["tech"],
        priority_score=0.55,
        priority_reason="tech",
        source_count=2,
    )

    pending = editorial.get_pending_news(limit=10)
    scores = [item.priority_score for item in pending]
    assert scores == sorted(scores, reverse=True)
    assert pending[0].title == "Major regulation story"
    assert pending[0].priority_score == pytest.approx(0.92)
