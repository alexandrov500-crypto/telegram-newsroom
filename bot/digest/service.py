from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from bot.digest.generator import generate_digest
from bot.processing.languages import LANG_EN, normalize_language_code
from bot.publisher import ChannelPublisher
from bot.publishing.channel_router import ChannelRouter
from bot.runtime.state import runtime_state
from bot.storage.digest_repository import (
    DIGEST_HOURLY,
    DIGEST_MORNING,
    DigestCandidate,
    DigestRepository,
)
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.entity_repository import EntityRepository
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.story_repository import StoryRepository
from bot.editorial.digest_ranker import DigestRanker, format_story_sections_html

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DigestRunResult:
    digest_type: str
    digest_id: int | None
    item_count: int
    published: bool
    skipped_empty: bool
    error: str | None = None


class DigestService:
    """Generate and optionally publish digests."""

    def __init__(
        self,
        digest_repo: DigestRepository,
        publisher: ChannelPublisher,
        entities: EntityRepository | None = None,
        analytics: AnalyticsRepository | None = None,
        localizations: LocalizationRepository | None = None,
        channel_router: ChannelRouter | None = None,
        story_repo: StoryRepository | None = None,
    ) -> None:
        self._digest_repo = digest_repo
        self._publisher = publisher
        self._entities = entities
        self._analytics = analytics
        self._localizations = localizations
        self._channel_router = channel_router
        self._story_ranker = (
            DigestRanker(story_repo) if story_repo is not None else None
        )

    def _localize_candidates(
        self,
        candidates: list[DigestCandidate],
        language: str,
    ) -> list[DigestCandidate]:
        lang = normalize_language_code(language) or LANG_EN
        if self._localizations is None or lang == LANG_EN:
            return candidates
        localized: list[DigestCandidate] = []
        for item in candidates:
            record = self._localizations.get_localization(item.id, lang)
            if record is None:
                localized.append(item)
                continue
            title = record.localized_headline or record.translated_title
            summary = record.translated_summary or item.summary
            localized.append(
                replace(item, title=title, summary=summary),
            )
        return localized

    def _since_for_type(self, digest_type: str) -> str | None:
        now = datetime.now(timezone.utc)
        if digest_type == DIGEST_HOURLY:
            return (now - timedelta(hours=1)).isoformat()
        if digest_type == DIGEST_MORNING:
            return (now - timedelta(hours=12)).isoformat()
        return None

    async def run_digest(
        self,
        digest_type: str,
        *,
        publish: bool = True,
        force_since: str | None = None,
        language: str | None = None,
    ) -> DigestRunResult:
        languages = (
            [normalize_language_code(language) or LANG_EN]
            if language
            else sorted(runtime_state.enabled_languages)
        )
        last_result = DigestRunResult(
            digest_type=digest_type,
            digest_id=None,
            item_count=0,
            published=False,
            skipped_empty=True,
        )

        for lang in languages:
            if lang is None:
                continue
            result = await self._run_digest_for_language(
                digest_type,
                lang,
                publish=publish,
                force_since=force_since,
            )
            last_result = result
        return last_result

    async def _run_digest_for_language(
        self,
        digest_type: str,
        language: str,
        *,
        publish: bool,
        force_since: str | None,
    ) -> DigestRunResult:
        logger.info(
            "event=digest_generation_started digest_type=%r language=%s",
            digest_type,
            language,
        )

        try:
            since_iso = force_since if force_since is not None else self._since_for_type(digest_type)
            candidates = self._digest_repo.get_undigested_published(
                limit=50,
                since_iso=since_iso,
                digest_type=digest_type,
                language=language,
            )
            candidates = self._localize_candidates(candidates, language)
            trending: list[str] = []
            if self._entities is not None:
                try:
                    trending = self._entities.trending_display_names(limit=5)
                except Exception:
                    logger.exception("event=digest_trending_failed")
            intelligence: dict[str, str | None] = {}
            if self._analytics is not None:
                try:
                    intelligence = self._analytics.get_digest_intelligence()
                except Exception:
                    logger.exception("event=digest_intelligence_failed")
            story_sections = None
            if self._story_ranker is not None:
                try:
                    story_sections = self._story_ranker.build_sections()
                    from bot.observability.metrics import set_digest_story_count

                    total_stories = sum(len(sec.stories) for sec in story_sections)
                    set_digest_story_count(total_stories)
                except Exception:
                    logger.exception("event=digest_story_rank_failed")

            generated = await generate_digest(
                digest_type,
                candidates,
                trending_entities=trending,
                digest_intelligence=intelligence,
                language=language,
                story_sections=story_sections,
            )
            if generated is None:
                logger.info(
                    "event=digest_empty_skipped digest_type=%r language=%s reason=no_candidates",
                    digest_type,
                    language,
                )
                return DigestRunResult(
                    digest_type=digest_type,
                    digest_id=None,
                    item_count=0,
                    published=False,
                    skipped_empty=True,
                )

            digest_id = self._digest_repo.create_digest(
                digest_type=digest_type,
                title=str(generated["title"]),
                content=str(generated["content"]),
                item_count=int(generated["item_count"]),
                language=language,
            )
            pending_ids = list(generated["pending_news_ids"])
            self._digest_repo.add_digest_items(digest_id, pending_ids)

            published = False
            error: str | None = None

            if publish and not runtime_state.dry_run_mode:
                channel_id = (
                    self._channel_router.channel_for(language)
                    if self._channel_router is not None
                    else self._publisher.channel_id
                )
                if channel_id is None:
                    error = "channel_not_configured"
                    logger.warning(
                        "event=digest_publish_failed digest_id=%d lang=%s reason=%r",
                        digest_id,
                        language,
                        error,
                    )
                else:
                    hero = generated.get("hero_media")
                    result = await self._publisher.publish_digest(
                        str(generated["content"]),
                        hero=hero,
                        channel_id=channel_id,
                    )
                    if result.success:
                        self._digest_repo.mark_digest_published(digest_id)
                        published = True
                        logger.info(
                            "event=multilingual_publish_success digest_id=%d "
                            "digest_type=%r lang=%s item_count=%d channel_id=%s",
                            digest_id,
                            digest_type,
                            language,
                            int(generated["item_count"]),
                            result.channel_id,
                        )
                    else:
                        error = result.error
                        logger.warning(
                            "event=multilingual_publish_failed digest_id=%d "
                            "digest_type=%r lang=%s error=%r",
                            digest_id,
                            digest_type,
                            language,
                            error,
                        )
            elif publish and runtime_state.dry_run_mode:
                logger.info(
                    "event=digest_publish_skipped digest_id=%d reason=dry_run lang=%s",
                    digest_id,
                    language,
                )

            logger.info(
                "event=digest_generation_completed digest_id=%d digest_type=%r "
                "lang=%s item_count=%d",
                digest_id,
                digest_type,
                language,
                int(generated["item_count"]),
            )
            return DigestRunResult(
                digest_type=digest_type,
                digest_id=digest_id,
                item_count=int(generated["item_count"]),
                published=published,
                skipped_empty=False,
                error=error,
            )
        except Exception as exc:
            logger.exception(
                "event=digest_generation_failed digest_type=%r language=%s",
                digest_type,
                language,
            )
            return DigestRunResult(
                digest_type=digest_type,
                digest_id=None,
                item_count=0,
                published=False,
                skipped_empty=False,
                error=repr(exc),
            )
