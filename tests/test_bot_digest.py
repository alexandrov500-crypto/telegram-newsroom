from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.digest import generator as gen
from bot.digest.service import DigestService
from bot.storage.db import init_database
from bot.storage.digest_repository import DIGEST_HOURLY, DigestCandidate, DigestRepository
from bot.storage.editorial_repository import EditorialRepository, STATUS_PUBLISHED


def _candidate(
    *,
    news_id: int,
    title: str,
    summary: str,
    priority: float,
    cluster_id: int | None = None,
    tags: list[str] | None = None,
) -> DigestCandidate:
    return DigestCandidate(
        id=news_id,
        title=title,
        summary=summary,
        link=f"https://example.com/{news_id}",
        tags=tags or ["news"],
        cluster_id=cluster_id,
        priority_score=priority,
        created_at="2026-05-15T10:00:00+00:00",
    )


def test_dedupe_by_cluster_keeps_highest_priority_first() -> None:
    items = [
        _candidate(news_id=1, title="A", summary="a", priority=0.9, cluster_id=10),
        _candidate(news_id=2, title="B", summary="b", priority=0.8, cluster_id=10),
        _candidate(news_id=3, title="C", summary="c", priority=0.7, cluster_id=11),
    ]
    deduped = gen.dedupe_by_cluster(items)
    assert [item.id for item in deduped] == [1, 3]


def test_generate_digest_selects_top_priority_items(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        _candidate(news_id=1, title="Low", summary="l", priority=0.2),
        _candidate(news_id=2, title="High", summary="h", priority=0.95, tags=["regulation"]),
        _candidate(news_id=3, title="Mid", summary="m", priority=0.6),
    ]
    monkeypatch.setattr(gen, "_optional_openai_intro", AsyncMock(return_value=None))

    async def run() -> dict | None:
        return await gen.generate_digest(DIGEST_HOURLY, items, max_items=2)

    result = asyncio.run(run())
    assert result is not None
    assert result["item_count"] == 2
    ids = result["pending_news_ids"]
    assert 2 in ids
    assert len(ids) == 2
    assert ids[0] == 2


def test_empty_digest_returns_none() -> None:
    async def run() -> dict | None:
        return await gen.generate_digest(DIGEST_HOURLY, [])

    assert asyncio.run(run()) is None


def test_digest_format_contains_sections() -> None:
    items = [
        _candidate(
            news_id=1,
            title="SEC approves Bitcoin ETF",
            summary="Regulators finalized custody rules.",
            priority=0.9,
            tags=["crypto", "etf"],
        ),
    ]
    title, content = gen.format_digest_body(digest_type="morning", items=items)
    assert "Morning News Digest" in title
    assert "1." in content
    assert "SEC approves Bitcoin ETF" in content
    assert "#crypto" in content


def test_repository_excludes_items_already_in_digest(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "digest.db")
    editorial = EditorialRepository(db_path)
    digest_repo = DigestRepository(db_path)

    news_id = editorial.enqueue_news(
        title="Story",
        summary="Body",
        link="https://example.com/story",
        tags=["ai"],
        priority_score=0.9,
        priority_reason="ai",
        source_count=1,
    )
    assert news_id is not None
    with editorial._connect() as conn:
        conn.execute(
            "UPDATE pending_news SET status = ? WHERE id = ?",
            (STATUS_PUBLISHED, news_id),
        )
        conn.commit()

    digest_id = digest_repo.create_digest(
        digest_type="hourly",
        title="t",
        content="c",
        item_count=1,
    )
    digest_repo.add_digest_items(digest_id, [news_id])

    remaining = digest_repo.get_undigested_published(limit=10)
    assert remaining == []


def test_service_skips_empty_digest(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "digest_empty.db")
    digest_repo = DigestRepository(db_path)
    publisher = MagicMock()
    publisher.channel_configured = True
    publisher.publish_digest = AsyncMock()
    publisher.send_to_channel = AsyncMock()
    service = DigestService(digest_repo, publisher)

    async def run():
        return await service.run_digest(DIGEST_HOURLY)

    result = asyncio.run(run())
    assert result.skipped_empty is True
    publisher.publish_digest.assert_not_called()
    publisher.send_to_channel.assert_not_called()
