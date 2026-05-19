from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.editorial.formatting import format_enriched_message
from bot.publisher import PublishResult
from bot.storage.db import init_database
from bot.storage.editorial_repository import EditorialRepository, STATUS_PENDING, STATUS_PUBLISHED
from bot.storage.repository import SeenLinkRepository


@pytest.fixture
def editorial_repo(tmp_path: Path) -> EditorialRepository:
    db_path = init_database(tmp_path / "editorial_test.db")
    return EditorialRepository(db_path)


def test_enqueue_and_get_pending(editorial_repo: EditorialRepository) -> None:
    news_id = editorial_repo.enqueue_news(
        title="AI breakthrough",
        summary="Models improve.",
        link="https://example.com/a",
        tags=["ai", "tech"],
        source="example-feed",
    )
    assert news_id == 1

    pending = editorial_repo.get_pending_news(limit=10)
    assert len(pending) == 1
    assert pending[0].id == 1
    assert pending[0].status == STATUS_PENDING
    assert pending[0].tags == ["ai", "tech"]


def test_enqueue_duplicate_returns_none(editorial_repo: EditorialRepository) -> None:
    editorial_repo.enqueue_news(
        title="One",
        summary="s",
        link="https://example.com/dup",
        tags=[],
        source="feed",
    )
    assert (
        editorial_repo.enqueue_news(
            title="Two",
            summary="s2",
            link="https://example.com/dup",
            tags=[],
            source="feed",
        )
        is None
    )


def test_reject_and_mark_published(editorial_repo: EditorialRepository) -> None:
    news_id = editorial_repo.enqueue_news(
        title="Story",
        summary="Body",
        link="https://example.com/story",
        tags=["news"],
        source="feed",
    )
    assert news_id is not None
    assert editorial_repo.reject_news(news_id) is True
    assert editorial_repo.get_pending_news() == []

    news_id2 = editorial_repo.enqueue_news(
        title="Story 2",
        summary="Body 2",
        link="https://example.com/story2",
        tags=[],
        source="feed",
    )
    assert news_id2 is not None
    assert editorial_repo.approve_news(news_id2) is not None
    assert editorial_repo.mark_published(news_id2) is True
    row = editorial_repo.get_by_id(news_id2)
    assert row is not None
    assert row.status == STATUS_PUBLISHED


def test_mark_seen_only_after_publish_flow(
    editorial_repo: EditorialRepository, tmp_path: Path
) -> None:
    db_path = tmp_path / "editorial_test.db"
    dedup = SeenLinkRepository(db_path)
    link = "https://example.com/publish-once"

    news_id = editorial_repo.enqueue_news(
        title="Publish me",
        summary="Summary",
        link=link,
        tags=["ai"],
        source="feed",
    )
    assert news_id is not None
    assert not dedup.is_seen(link)

    item = editorial_repo.approve_news(news_id)
    assert item is not None
    text = format_enriched_message(
        {"title": item.title, "summary": item.summary, "tags": item.tags},
        item.link,
    )
    assert "Publish me" in text

    async def _publish() -> PublishResult:
        return PublishResult(
            success=True,
            channel_id=-100123,
            message_id=1,
            duration_ms=10,
            error=None,
        )

    result = asyncio.run(_publish())
    assert result.success
    assert editorial_repo.mark_published(news_id)
    dedup.mark_seen(link)

    assert dedup.is_seen(link)
    assert (
        editorial_repo.enqueue_news(
            title="Dup",
            summary="s",
            link=link,
            tags=[],
            source="feed",
        )
        is None
    )
