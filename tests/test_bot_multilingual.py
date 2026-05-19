from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from bot.digest.generator import digest_title_for_language, format_digest_body
from bot.editorial.localization_pipeline import apply_localization_pipeline
from bot.editorial.multilingual_publish import resolve_localized_publish_text
from bot.processing.entities import canonical_entity_key, resolve_entity
from bot.processing.languages import LANG_EN, LANG_RU, SUPPORTED_LANGUAGES
from bot.processing.translation import (
    build_localized_story,
    detect_language,
    localize_headline,
    translate_story,
)
from bot.publishing.channel_router import ChannelRouter
from bot.publisher import ChannelPublisher
from bot.runtime.state import runtime_state
from bot.storage.db import init_database
from bot.storage.digest_repository import DigestCandidate, DigestRepository
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.localization_repository import LocalizationRepository


def test_supported_languages_are_ru_en_only() -> None:
    assert SUPPORTED_LANGUAGES == (LANG_RU, LANG_EN)


def test_detect_language_cyrillic() -> None:
    assert detect_language("SEC официально одобрила Bitcoin ETF") == LANG_RU


def test_detect_language_latin_defaults_english() -> None:
    assert detect_language("SEC approves Bitcoin ETF") == LANG_EN


def test_static_translation_sec_headline_ru() -> None:
    async def run() -> tuple[str, str]:
        return await translate_story(
            "SEC approves Bitcoin ETF",
            "Regulators approved the product.",
            source_lang=LANG_EN,
            target_lang=LANG_RU,
        )

    title, _ = asyncio.run(run())
    assert "SEC" in title
    assert "одобрила" in title


def test_entity_cross_language_sec_alias() -> None:
    entity = resolve_entity("Комиссия SEC", "organization")
    assert entity is not None
    assert entity.display_name == "SEC"
    assert canonical_entity_key("Комиссия SEC") == canonical_entity_key("SEC")


def test_localization_repository_upsert_and_list(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "ml.db")
    editorial = EditorialRepository(db_path)
    localizations = LocalizationRepository(db_path)
    news_id = editorial.enqueue_news(
        title="SEC approves Bitcoin ETF",
        summary="US regulators approved the product.",
        link="https://example.com/sec-etf",
        tags=["crypto"],
        source_language=LANG_EN,
    )
    assert news_id is not None
    localizations.upsert_localization(
        pending_news_id=news_id,
        language=LANG_RU,
        translated_title="SEC одобрила Bitcoin ETF",
        translated_summary="Регуляторы США одобрили продукт.",
        localized_headline="SEC официально одобрила Bitcoin ETF",
        localized_hook="📈 Рынки реагируют",
    )
    record = localizations.get_localization(news_id, LANG_RU)
    assert record is not None
    assert "одобрила" in record.localized_headline


def test_channel_router_maps_ru_en() -> None:
    bot = MagicMock()
    publisher = ChannelPublisher(bot, None)
    router = ChannelRouter(
        publisher,
        {"en": -100111, "ru": -100222},
        default_channel_id=-100111,
    )
    assert router.channel_for("ru") == -100222
    assert router.channel_for("en") == -100111


def test_localization_pipeline_generates_ru_variant(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "ml_pipeline.db")
    editorial = EditorialRepository(db_path)
    localizations = LocalizationRepository(db_path)
    news_id = editorial.enqueue_news(
        title="SEC approves Bitcoin ETF",
        summary="US regulators approved the product.",
        link="https://example.com/sec-etf-pipe",
        hook_line="📈 Markets react",
        source_language=LANG_EN,
    )
    assert news_id is not None
    runtime_state.enabled_languages = {LANG_EN, LANG_RU}
    try:
        asyncio.run(
            apply_localization_pipeline(
                pending_news_id=news_id,
                title="SEC approves Bitcoin ETF",
                summary="US regulators approved the product.",
                hook_line="📈 Markets react",
                editorial=editorial,
                localizations=localizations,
            )
        )
    finally:
        runtime_state.enabled_languages = {LANG_EN}
    rows = localizations.list_for_pending(news_id)
    assert any(row.language == LANG_RU for row in rows)


def test_multilingual_digest_title_ru() -> None:
    title = digest_title_for_language("morning", LANG_RU)
    assert "дайджест" in title.lower()


def test_build_localized_story_ru() -> None:
    async def run():
        return await build_localized_story(
            title="SEC approves Bitcoin ETF",
            summary="Approved.",
            hook="📈 Markets react",
            source_lang=LANG_EN,
            target_lang=LANG_RU,
        )

    story = asyncio.run(run())
    assert story.language == LANG_RU
    assert "одобрила" in story.headline
