from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.processing.headlines import (
    CAPTION_HYBRID,
    resolve_publish_headline,
    resolve_publish_hook,
)
from bot.processing.languages import LANG_EN, normalize_language_code
from bot.processing.translation import target_languages_for_publish
from bot.publisher import ChannelPublisher, PublishResult
from bot.publishing.channel_router import ChannelRouter
from bot.runtime.state import runtime_state
from bot.storage.editorial_repository import PendingNewsItem
from bot.storage.localization_repository import LocalizationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocalizedPublishText:
    language: str
    title: str
    summary: str | None
    headline: str
    hook: str | None
    original_title: str


def resolve_localized_publish_text(
    item: PendingNewsItem,
    language: str,
    localizations: LocalizationRepository | None,
) -> LocalizedPublishText:
    """Resolve publish copy for a language; fail-open to source text."""
    lang = normalize_language_code(language) or LANG_EN
    source = normalize_language_code(item.source_language) or LANG_EN

    if lang == source:
        headline = resolve_publish_headline(
            original_title=item.title,
            optimized_headline=item.optimized_headline,
            caption_style=runtime_state.caption_style,
            ai_headlines_enabled=runtime_state.ai_headlines_enabled,
        )
        hook = resolve_publish_hook(
            item.hook_line,
            ai_headlines_enabled=runtime_state.ai_headlines_enabled,
            caption_style=runtime_state.caption_style,
        )
        return LocalizedPublishText(
            language=lang,
            title=item.title,
            summary=item.summary,
            headline=headline,
            hook=hook,
            original_title=item.title,
        )

    if localizations is not None:
        loc = localizations.get_localization(item.id, lang)
        if loc is not None:
            headline = loc.localized_headline or loc.translated_title
            return LocalizedPublishText(
                language=lang,
                title=loc.translated_title,
                summary=loc.translated_summary,
                headline=headline,
                hook=loc.localized_hook or item.hook_line,
                original_title=item.title,
            )

    if item.target_language == lang and item.translated_title:
        return LocalizedPublishText(
            language=lang,
            title=item.translated_title,
            summary=item.translated_summary,
            headline=item.localized_headline or item.translated_title,
            hook=item.localized_hook or item.hook_line,
            original_title=item.title,
        )

    headline = resolve_publish_headline(
        original_title=item.title,
        optimized_headline=item.optimized_headline,
        caption_style=runtime_state.caption_style,
        ai_headlines_enabled=runtime_state.ai_headlines_enabled,
    )
    hook = resolve_publish_hook(
        item.hook_line,
        ai_headlines_enabled=runtime_state.ai_headlines_enabled,
        caption_style=runtime_state.caption_style,
    )
    return LocalizedPublishText(
        language=lang,
        title=item.title,
        summary=item.summary,
        headline=headline,
        hook=hook,
        original_title=item.title,
    )


async def publish_to_language_channel(
    item: PendingNewsItem,
    language: str,
    *,
    publisher: ChannelPublisher,
    router: ChannelRouter | None,
    localizations: LocalizationRepository | None,
    trending_entities: list[str] | None = None,
) -> PublishResult:
    """Publish one localized variant. Never raises."""
    lang = normalize_language_code(language) or LANG_EN
    channel_id = router.channel_for(lang) if router is not None else publisher.channel_id
    if channel_id is None:
        return PublishResult(
            success=False,
            duration_ms=0,
            channel_id=None,
            error="channel_not_configured",
        )

    text = resolve_localized_publish_text(item, lang, localizations)
    media_type = item.media_type
    media_url = item.media_url
    thumbnail_url = item.thumbnail_url
    try:
        from bot.editorial.media_enrichment import enrich_publish_media

        media = await enrich_publish_media(item)
        if media.has_media:
            media_type = media.media_type
            media_url = media.media_url
            thumbnail_url = media.thumbnail_url or thumbnail_url
    except Exception:
        logger.debug("event=media_enrich_skipped pending_news_id=%s", item.id)

    try:
        result = await publisher.publish_news(
            title=text.headline,
            summary=text.summary,
            link=item.link,
            tags=item.tags,
            source=item.source,
            media_type=media_type,
            media_url=media_url,
            thumbnail_url=thumbnail_url,
            trending_entities=trending_entities or [],
            hook_line=text.hook,
            original_title=text.original_title,
            show_original_subtitle=runtime_state.caption_style == CAPTION_HYBRID,
            channel_id=channel_id,
        )
        if result.success:
            from bot.observability.metrics import record_publish_success

            record_publish_success(lang, result.duration_ms / 1000.0)
            logger.info(
                "event=multilingual_publish_success pending_news_id=%d lang=%s channel_id=%s",
                item.id,
                lang,
                channel_id,
            )
        else:
            from bot.observability.metrics import record_publish_failure

            record_publish_failure(lang, result.error or "unknown")
            logger.warning(
                "event=multilingual_publish_failed pending_news_id=%d lang=%s error=%r",
                item.id,
                lang,
                result.error,
            )
        return result
    except Exception as exc:
        logger.exception(
            "event=multilingual_publish_failed pending_news_id=%d lang=%s",
            item.id,
            lang,
        )
        return PublishResult(
            success=False,
            duration_ms=0,
            channel_id=channel_id,
            error=repr(exc),
        )


def languages_to_publish(item: PendingNewsItem) -> list[str]:
    return target_languages_for_publish(
        item.source_language,
        runtime_state.enabled_languages,
    )
