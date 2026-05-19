from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from bot.editorial.formatting import format_publish_caption, format_publish_message
from bot.editorial.hashtags import normalize_hashtags
from bot.editorial.links import canonical_article_url
from bot.editorial.presentation import build_publish_presentation
from bot.editorial.source_registry import format_source_attribution, resolve_source_display
from bot.editorial.templates import resolve_editorial_template
from bot.processing.media import MEDIA_NONE, MediaInfo
from bot.storage.editorial_repository import PendingNewsItem


def test_source_registry_ap_display() -> None:
    src = resolve_source_display("ap")
    assert src.name == "Associated Press"
    assert src.short == "AP"
    assert format_source_attribution("ap") == "Associated Press (AP)"


def test_canonical_url_strips_tracking() -> None:
    raw = (
        "https://apnews.com/article/foo?utm_source=twitter&fbclid=abc"
        "&pilot=1&keep=1"
    )
    clean = canonical_article_url(raw)
    assert "utm_" not in clean
    assert "fbclid" not in clean
    assert "pilot" not in clean
    assert "keep=1" in clean


def test_hashtag_dedupe_and_cap() -> None:
    tags = normalize_hashtags(
        ["economy", "Economy", "inflation", "markets", "jobs", "gdp"],
        source="ap",
    )
    assert len(tags) <= 4
    assert tags[0] == "Economy"


def test_presentation_html_structure() -> None:
    body = format_publish_message(
        title="Fed holds rates steady",
        summary="Central bankers cited inflation progress.",
        link="https://apnews.com/article/x?utm_campaign=test",
        tags=["economy", "inflation"],
        source="ap",
        hook_line="Policy path unchanged",
    )
    assert "Associated Press" in body
    assert "(AP)" in body
    assert "Fed holds rates steady" in body
    assert "Read more" in body
    assert "utm_campaign" not in body
    assert "#Economy" in body or "#Inflation" in body
    assert "https://apnews.com/article/x" in body


def test_economy_template_default() -> None:
    pres = build_publish_presentation(
        title="Jobs report beats forecast",
        summary="Hiring accelerated.",
        link="https://example.com/jobs",
        tags=["labor"],
        source="reuters",
    )
    assert pres.template.key == "economy"
    caption = format_publish_caption(
        title="Jobs report beats forecast",
        summary="Hiring accelerated.",
        link="https://example.com/jobs",
        tags=["labor"],
        source="reuters",
    )
    assert "📊" in caption


def test_media_enrich_fail_open() -> None:
    from bot.editorial.media_enrichment import enrich_publish_media

    item = PendingNewsItem(
        id=1,
        title="Test",
        summary="Summary",
        link="https://example.com/story",
        tags=["economy"],
        source="ap",
        created_at="2026-01-01T00:00:00Z",
        status="approved",
    )

    async def run():
        with patch(
            "bot.editorial.media_enrichment.fetch_opengraph_media",
            new=AsyncMock(side_effect=TimeoutError("slow")),
        ):
            return await enrich_publish_media(item)

    media = asyncio.run(run())
    assert media.media_type == MEDIA_NONE


def test_media_enrich_uses_existing_item_media() -> None:
    from bot.editorial.media_enrichment import enrich_publish_media

    item = PendingNewsItem(
        id=2,
        title="Photo story",
        summary="Summary",
        link="https://example.com/story",
        tags=[],
        source="ap",
        created_at="2026-01-01T00:00:00Z",
        status="approved",
        media_type="photo",
        media_url="https://cdn.example.com/hero.jpg",
    )

    async def run():
        fetch = AsyncMock(return_value=MediaInfo.none())
        with patch("bot.editorial.media_enrichment.fetch_opengraph_media", new=fetch):
            return await enrich_publish_media(item), fetch

    media, fetch = asyncio.run(run())
    assert media.media_url == "https://cdn.example.com/hero.jpg"
    fetch.assert_not_called()
