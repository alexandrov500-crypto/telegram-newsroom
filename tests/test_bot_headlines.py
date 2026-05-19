from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot

from bot.editorial.formatting import TELEGRAM_CAPTION_MAX, format_publish_caption
from bot.processing.headlines import (
    CAPTION_HYBRID,
    CAPTION_ORIGINAL,
    STYLE_LONG,
    STYLE_MEDIUM,
    STYLE_SHORT,
    generate_hook_line,
    generate_optimized_headline,
    optimize_story_headlines,
    resolve_publish_headline,
    resolve_publish_hook,
)
from bot.publisher import ChannelPublisher


def test_short_medium_long_limits() -> None:
    title = "OpenAI launches major model update with improved reasoning capabilities worldwide"
    summary = "The company announced new capabilities for enterprise customers."
    entities = ["OpenAI"]

    short = generate_optimized_headline(
        title=title, summary=summary, entities=entities, mode=STYLE_SHORT
    )
    medium = generate_optimized_headline(
        title=title, summary=summary, entities=entities, mode=STYLE_MEDIUM
    )
    long_headline = generate_optimized_headline(
        title=title, summary=summary, entities=entities, mode=STYLE_LONG
    )

    assert len(short) <= 80
    assert len(medium) <= 140
    assert len(long_headline) <= 240
    assert "OpenAI" in medium


def test_entity_preserved_in_rule_headline() -> None:
    headline = generate_optimized_headline(
        title="Regulators finalize custody guidance",
        summary="SEC updated ETF custody rules for institutions.",
        entities=["SEC", "Bitcoin ETF"],
        mode=STYLE_MEDIUM,
    )
    assert "SEC" in headline


def test_hook_generation() -> None:
    hook = generate_hook_line(
        title="SEC approves Bitcoin ETF",
        summary="Regulators finalized custody rules.",
        entities=["SEC", "Bitcoin"],
        tags=["crypto", "regulation"],
    )
    assert hook is not None
    assert len(hook) <= 48


def test_optimize_story_headlines_fallback() -> None:
    result = asyncio.run(
        optimize_story_headlines(
            title="Bitcoin surges after ETF news",
            summary="Markets reacted to regulatory approval.",
            tags=["crypto"],
            entities=["Bitcoin"],
            mode=STYLE_MEDIUM,
            use_llm=False,
        )
    )
    assert result.optimized_headline
    assert len(result.optimized_headline) <= 140
    assert result.used_fallback is True


def test_resolve_publish_headline_modes() -> None:
    assert (
        resolve_publish_headline(
            original_title="Original title",
            optimized_headline="Optimized title",
            caption_style=CAPTION_ORIGINAL,
            ai_headlines_enabled=True,
        )
        == "Original title"
    )
    assert (
        resolve_publish_headline(
            original_title="Original title",
            optimized_headline="Optimized title",
            caption_style="optimized",
            ai_headlines_enabled=True,
        )
        == "Optimized title"
    )
    assert (
        resolve_publish_headline(
            original_title="Original title",
            optimized_headline=None,
            caption_style="optimized",
            ai_headlines_enabled=True,
        )
        == "Original title"
    )


def test_publisher_uses_optimized_caption() -> None:
    async def run():
        bot = MagicMock(spec=Bot)
        sent = MagicMock(message_id=1)
        bot.send_message = AsyncMock(return_value=sent)
        publisher = ChannelPublisher(bot, channel_id=-1001)
        return await publisher.publish_news(
            title="SEC approves Bitcoin ETF",
            summary="Regulators finalized custody guidance.",
            link="https://example.com/etf",
            tags=["crypto"],
            hook_line="📈 Markets react",
            original_title="Original SEC headline",
            show_original_subtitle=True,
        ), bot

    result, bot = asyncio.run(run())
    assert result.success
    body = bot.send_message.await_args.kwargs["text"]
    assert "📈 Markets react" in body
    assert "SEC approves Bitcoin ETF" in body
    assert "Original SEC headline" in body


def test_caption_truncation_with_hook() -> None:
    caption = format_publish_caption(
        title="Headline",
        summary="word " * 300,
        link="https://example.com/x",
        tags=["ai"],
        hook_line="🔥 Major AI update",
    )
    assert len(caption) <= TELEGRAM_CAPTION_MAX
    assert "🔥 Major AI update" in caption


def test_resolve_publish_hook_disabled_for_original() -> None:
    assert (
        resolve_publish_hook(
            "🔥 Major AI update",
            ai_headlines_enabled=True,
            caption_style=CAPTION_ORIGINAL,
        )
        is None
    )
