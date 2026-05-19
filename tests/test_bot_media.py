from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot

from bot.editorial.formatting import (
    TELEGRAM_CAPTION_MAX,
    format_publish_caption,
    truncate_html_safe,
)
from bot.ingestion.pipeline import IngestOutcome, ingest_news_item
from bot.ingestion.rss import NewsItem
from bot.digest.generator import generate_digest
from bot.processing.media import (
    extract_telegram_media,
    MEDIA_NONE,
    MEDIA_PHOTO,
    MEDIA_VIDEO,
    MediaInfo,
    choose_best_media,
    extract_og_image_from_html,
    extract_rss_media,
    select_digest_hero_media,
    validate_media,
)
from bot.storage.digest_repository import DIGEST_HOURLY, DigestCandidate
from bot.publisher import ChannelPublisher
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.db import init_database
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.repository import MemoryLinkDedup


def test_extract_rss_enclosure_and_og() -> None:
    entry = {
        "enclosures": [
            {"href": "https://cdn.example.com/photo.jpg", "type": "image/jpeg", "length": "12000"}
        ],
        "summary": '<html><meta property="og:image" content="https://cdn.example.com/og.jpg"/></html>',
    }
    media = extract_rss_media(entry)
    assert media.media_type == MEDIA_PHOTO
    assert media.media_url == "https://cdn.example.com/photo.jpg"


def test_skip_gif_and_tracking_pixels() -> None:
    entry = {
        "enclosures": [
            {"href": "https://cdn.example.com/ad.gif", "type": "image/gif", "length": "9000"},
            {
                "href": "https://doubleclick.net/pixel?id=1",
                "type": "image/png",
                "length": "9000",
            },
        ],
    }
    media = extract_rss_media(entry)
    assert media.media_type == MEDIA_NONE


def test_og_image_fallback() -> None:
    html = '<meta content="https://img.example.com/story.png" property="og:image"/>'
    assert extract_og_image_from_html(html) == "https://img.example.com/story.png"


def test_choose_best_media_priority() -> None:
    telegram = MediaInfo(
        media_type=MEDIA_PHOTO,
        media_url="local:///tmp/tg.jpg",
        media_ref='{"kind":"photo"}',
    )
    rss = MediaInfo(
        media_type=MEDIA_PHOTO,
        media_url="https://cdn.example.com/rss.jpg",
    )
    best = choose_best_media(telegram, rss)
    assert best.media_url == "local:///tmp/tg.jpg"


def test_caption_truncation_safe() -> None:
    long_summary = "word " * 400
    caption = format_publish_caption(
        title="Title",
        summary=long_summary,
        link="https://example.com/x",
        tags=["ai", "crypto"],
        source="Reuters",
    )
    assert len(caption) <= TELEGRAM_CAPTION_MAX
    assert "…" in caption
    truncated = truncate_html_safe("alpha beta gamma delta epsilon", 12)
    assert len(truncated) <= 12
    assert truncated.endswith("…")


def test_publish_photo_success() -> None:
    async def run():
        bot = MagicMock(spec=Bot)
        sent = MagicMock(message_id=99)
        bot.send_photo = AsyncMock(return_value=sent)
        bot.send_message = AsyncMock()
        publisher = ChannelPublisher(bot, channel_id=-100123)
        return await publisher.publish_news(
            title="SEC approves Bitcoin ETF",
            summary="Regulators finalized custody guidance.",
            link="https://example.com/etf",
            tags=["crypto"],
            source="Reuters",
            media_type=MEDIA_PHOTO,
            media_url="https://cdn.example.com/etf.jpg",
        ), bot

    result, bot = asyncio.run(run())
    assert result.success
    assert result.used_media
    bot.send_photo.assert_awaited_once()
    bot.send_message.assert_not_awaited()


def test_publish_video_success() -> None:
    async def run():
        bot = MagicMock(spec=Bot)
        sent = MagicMock(message_id=7)
        bot.send_video = AsyncMock(return_value=sent)
        bot.send_message = AsyncMock()
        publisher = ChannelPublisher(bot, channel_id=-100123)
        return await publisher.publish_news(
            title="Launch video",
            summary="Product demo.",
            link="https://example.com/v",
            tags=["tech"],
            media_type=MEDIA_VIDEO,
            media_url="https://cdn.example.com/demo.mp4",
            thumbnail_url="https://cdn.example.com/thumb.jpg",
        ), bot

    result, bot = asyncio.run(run())
    assert result.success
    bot.send_video.assert_awaited_once()


def test_broken_media_falls_back_to_text() -> None:
    async def run():
        bot = MagicMock(spec=Bot)
        bot.send_photo = AsyncMock(side_effect=Exception("upload failed"))
        sent = MagicMock(message_id=3)
        bot.send_message = AsyncMock(return_value=sent)
        publisher = ChannelPublisher(bot, channel_id=-100123)
        return await publisher.publish_news(
            title="Broken image",
            summary="Still publishable.",
            link="https://example.com/broken",
            tags=["news"],
            media_type=MEDIA_PHOTO,
            media_url="https://cdn.example.com/missing.jpg",
        ), bot

    result, bot = asyncio.run(run())
    assert result.success
    assert result.media_fallback
    bot.send_message.assert_awaited()


def test_rejects_tiny_images() -> None:
    tiny = MediaInfo(
        media_type=MEDIA_PHOTO,
        media_url="https://cdn.example.com/small.jpg",
        width=100,
        height=80,
    )
    assert validate_media(tiny).media_type == MEDIA_NONE


def test_caption_includes_trending_entities() -> None:
    caption = format_publish_caption(
        title="SEC approves Bitcoin ETF",
        summary="Regulators updated custody rules.",
        link="https://example.com/etf",
        tags=["crypto"],
        trending_entities=["SEC", "Bitcoin ETF"],
    )
    assert "Trending:" in caption
    assert "SEC" in caption
    assert "Bitcoin ETF" in caption


def test_digest_hero_media_selection() -> None:
    candidates = [
        MediaInfo(media_type=MEDIA_NONE),
        MediaInfo(
            media_type=MEDIA_PHOTO,
            media_url="https://cdn.example.com/hero.jpg",
            width=1280,
            height=720,
        ),
        MediaInfo(
            media_type=MEDIA_PHOTO,
            media_url="https://cdn.example.com/alt.jpg",
            width=640,
            height=480,
        ),
    ]
    hero = select_digest_hero_media(candidates)
    assert hero.media_url == "https://cdn.example.com/hero.jpg"


def test_digest_generation_includes_hero(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "bot.digest.generator._optional_openai_intro",
        AsyncMock(return_value=None),
    )
    items = [
        DigestCandidate(
            id=1,
            title="Story",
            summary="Summary",
            link="https://example.com/1",
            tags=["news"],
            cluster_id=None,
            priority_score=0.9,
            created_at="2026-05-15T10:00:00+00:00",
            media_type=MEDIA_PHOTO,
            media_url="https://cdn.example.com/digest-hero.jpg",
            media_width=1200,
            media_height=800,
        )
    ]

    async def run():
        return await generate_digest(DIGEST_HOURLY, items)

    result = asyncio.run(run())
    assert result is not None
    hero = result["hero_media"]
    assert hero.media_type == MEDIA_PHOTO
    assert hero.media_url == "https://cdn.example.com/digest-hero.jpg"


def test_telegram_media_extraction_photo() -> None:
    photo_size = MagicMock(w=1280, h=720)
    photo = MagicMock(sizes=[photo_size])
    message = MagicMock(id=55, photo=photo, video=None, document=None, fwd_from=None, message="Caption")
    media = extract_telegram_media(message)
    assert media.media_type == MEDIA_PHOTO
    assert media.width == 1280


def test_ingestion_preserves_media_metadata(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "media_queue.db")
    editorial = EditorialRepository(db_path)
    clusters = ClusterRepository(db_path)
    dedup = MemoryLinkDedup()

    item = NewsItem(
        title="Photo story",
        link="https://example.com/photo-story",
        published=None,
        source="test-feed",
        media_type=MEDIA_PHOTO,
        media_url="https://cdn.example.com/hero.jpg",
        thumbnail_url="https://cdn.example.com/thumb.jpg",
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
    pending = editorial.get_pending_news(limit=1)[0]
    assert pending.media_type == MEDIA_PHOTO
    assert pending.media_url == "https://cdn.example.com/hero.jpg"
    assert pending.thumbnail_url == "https://cdn.example.com/thumb.jpg"
