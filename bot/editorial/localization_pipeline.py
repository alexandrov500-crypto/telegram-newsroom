from __future__ import annotations

import logging

from bot.processing.languages import LANG_EN
from bot.processing.translation import build_localized_story, detect_language
from bot.runtime.state import runtime_state
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.localization_repository import LocalizationRepository

logger = logging.getLogger(__name__)


async def apply_localization_pipeline(
    *,
    pending_news_id: int,
    title: str,
    summary: str | None,
    hook_line: str | None,
    editorial: EditorialRepository,
    localizations: LocalizationRepository,
) -> None:
    """Detect source language and generate enabled localizations. Fail-open."""
    try:
        source_lang = detect_language(f"{title}\n{summary or ''}")
        editorial.update_language_fields(
            pending_news_id,
            source_language=source_lang,
        )

        targets = {
            lang
            for lang in runtime_state.enabled_languages
            if lang != source_lang
        }

        for target_lang in sorted(targets):
            if not runtime_state.is_language_enabled(target_lang):
                continue
            story = await build_localized_story(
                title=title,
                summary=summary,
                hook=hook_line,
                source_lang=source_lang,
                target_lang=target_lang,
            )
            localizations.upsert_localization(
                pending_news_id=pending_news_id,
                language=story.language,
                translated_title=story.title,
                translated_summary=story.summary,
                localized_headline=story.headline,
                localized_hook=story.hook,
            )
            if (
                runtime_state.primary_publish_language == target_lang
                or (
                    runtime_state.primary_publish_language is None
                    and target_lang != source_lang
                )
            ):
                editorial.update_language_fields(
                    pending_news_id,
                    target_language=target_lang,
                    translated_title=story.title,
                    translated_summary=story.summary,
                    localized_headline=story.headline,
                    localized_hook=story.hook,
                )
        logger.info(
            "event=localization_applied pending_news_id=%d source=%s targets=%d",
            pending_news_id,
            source_lang,
            len(targets),
        )
    except Exception:
        logger.exception(
            "event=localization_failed pending_news_id=%d",
            pending_news_id,
        )
