from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.ingestion import normalize as norm
from bot.ingestion.pipeline import IngestOutcome, ingest_news_item
from bot.ingestion.rss import NewsItem
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.db import init_database
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.repository import MemoryLinkDedup
from bot.storage.telegram_seen_repository import TelegramSeenRepository


def test_duplicate_telegram_messages_skipped(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "tg_seen.db")
    repo = TelegramSeenRepository(db_path)
    assert not repo.is_seen("@news", 42)
    repo.mark_seen("@news", 42)
    assert repo.is_seen("@news", 42)


def test_seen_messages_persist_after_restart(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "tg_restart.db")
    TelegramSeenRepository(db_path).mark_seen("@channel", 100)
    reloaded = TelegramSeenRepository(db_path)
    assert reloaded.is_seen("@channel", 100)


def test_malformed_messages_ignored() -> None:
    assert norm.normalize_telegram_text("") is None
    assert norm.normalize_telegram_text("   ") is None
    assert (
        norm.message_to_normalized(
            text="short",
            channel_display="Test",
            channel_key="@test",
            message_id=2,
        )
        is None
    )
    assert norm.normalize_telegram_text("Join @spam for promo code") is None
    assert norm.message_to_normalized(
        text="Join @spam channel now",
        channel_display="Test",
        channel_key="@test",
        message_id=1,
    ) is None


def test_valid_message_normalization() -> None:
    text = (
        "SEC approves Bitcoin ETF\n\n"
        "Regulators finalized updated custody guidance for institutional products."
    )
    normalized = norm.message_to_normalized(
        text=text,
        channel_display="CoinDesk",
        channel_key="@coindesk",
        message_id=99,
    )
    assert normalized is not None
    assert normalized.title.startswith("SEC approves")
    assert normalized.link == "https://t.me/coindesk/99"


def test_queue_integration_via_pipeline(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "tg_pipeline.db")
    editorial = EditorialRepository(db_path)
    clusters = ClusterRepository(db_path)
    dedup = MemoryLinkDedup()

    item = NewsItem(
        title="OpenAI launches new model",
        link="https://t.me/technews/12",
        published=None,
        source="telegram:@technews",
    )

    async def run():
        return await ingest_news_item(
            item,
            dedup=dedup,
            editorial=editorial,
            clusters=clusters,
        )

    result = asyncio.run(run())
    assert result.outcome == IngestOutcome.ENQUEUED
    pending = editorial.get_pending_news(limit=5)
    assert len(pending) == 1
    assert pending[0].link == item.link


def test_normalize_channel_ref_variants() -> None:
    assert norm.normalize_channel_ref("examplechannel") == "@examplechannel"
    assert norm.normalize_channel_ref("@ExampleChannel") == "@examplechannel"
    assert norm.normalize_channel_ref("-1001234567890") == "-1001234567890"
