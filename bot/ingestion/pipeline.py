from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from bot.ingestion.rss import NewsItem
from bot.processing.media import MEDIA_NONE, MediaInfo, validate_media
from bot.processing.priority import calculate_priority
from bot.processing.entities import extract_entities
from bot.processing.headlines import CAPTION_OPTIMIZED, optimize_story_headlines
from bot.processing.summarizer import summarize_news
from bot.runtime.state import runtime_state
from bot.storage.cluster_repository import ClusterAttachOutcome, ClusterRepository
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.repository import LinkDedup
from bot.editorial.agent_service import EditorialAgentService
from bot.editorial.localization_pipeline import apply_localization_pipeline
from bot.editorial.story_memory import StoryMemoryService
from bot.adaptive.service import AdaptiveOperationsService
from bot.signals.signal_service import SignalIntelligenceService
from bot.signals.types import EditorialAction
from bot.processing.translation import detect_language
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.entity_repository import EntityRepository
from bot.storage.source_repository import SourceProfile, SourceRepository

logger = logging.getLogger(__name__)


class IngestOutcome(str, Enum):
    ENQUEUED = "enqueued"
    CLUSTER_MATCHED = "cluster_matched"
    DUPLICATE_SKIPPED = "duplicate_skipped"
    CLUSTER_DUPLICATE = "cluster_duplicate"


@dataclass(frozen=True)
class IngestResult:
    outcome: IngestOutcome
    news_id: int | None = None
    cluster_id: int | None = None


async def _summarize_for_queue(
    item: NewsItem,
    *,
    story_context: dict[str, str] | None = None,
) -> dict:
    try:
        return await summarize_news(
            item.title,
            item.link,
            item.source,
            story_context=story_context,
        )
    except Exception:
        logger.exception(
            "event=processing_failed fallback=title_only link=%r",
            item.link,
        )
        return {"title": item.title, "summary": f"Short summary: {item.title}", "tags": []}


async def _optimize_headlines_for_story(
    *,
    title: str,
    summary: str,
    tags: list[str],
    analytics: AnalyticsRepository | None = None,
) -> tuple[str | None, str | None, str]:
    if not runtime_state.ai_headlines_enabled:
        return None, None, CAPTION_OPTIMIZED
    try:
        entity_result = await extract_entities(
            title,
            summary,
            tags,
            use_openai=False,
        )
        entity_names = [
            entity.display_name
            for entity in entity_result.entities
            if entity.entity_type != "topic"
        ][:6]
        hook_signals = []
        if analytics is not None:
            try:
                hook_signals = analytics.hook_signals_for_generation()
            except Exception:
                hook_signals = []
        headline_pkg = await optimize_story_headlines(
            title=title,
            summary=summary,
            tags=tags,
            entities=entity_names,
            mode=runtime_state.headline_mode,
            use_llm=runtime_state.ai_headlines_enabled,
            hook_signals=hook_signals,
        )
        return (
            headline_pkg.optimized_headline,
            headline_pkg.hook_line,
            runtime_state.caption_style,
        )
    except Exception:
        logger.exception("event=headline_fallback_used reason=pipeline_error")
        return None, None, CAPTION_OPTIMIZED


async def _score_story(
    *,
    title: str,
    summary: str,
    tags: list[str],
    source: str | None,
    clusters: ClusterRepository,
    cluster_id: int | None,
    sources: SourceRepository | None,
    source_profile: SourceProfile | None = None,
    analytics: AnalyticsRepository | None = None,
) -> tuple[float, str, int]:
    view = clusters.get_cluster_view(cluster_id)
    source_count = len(view.sources) if view.sources else 1

    source_trust: float | None = None
    source_approval_ratio: float | None = None
    if source_profile is not None:
        source_trust = source_profile.trust_score
        source_approval_ratio = source_profile.approval_ratio
    elif sources is not None:
        profile = sources.get_profile(source)
        source_trust = profile.trust_score
        source_approval_ratio = profile.approval_ratio

    topic_virality = None
    if analytics is not None:
        try:
            topic_virality = analytics.topic_virality(tags)
        except Exception:
            topic_virality = None

    priority = await calculate_priority(
        title=title,
        summary=summary,
        tags=tags,
        source_count=source_count,
        cluster_variants=view.variant_count,
        source_name=source,
        source_trust=source_trust,
        source_approval_ratio=source_approval_ratio,
        topic_virality=topic_virality,
    )
    score = float(priority.get("score", 0.5))
    reason = str(priority.get("reason", "default fallback"))
    return score, reason, max(source_count, view.variant_count)


async def _refresh_pending_cluster_priority(
    *,
    editorial: EditorialRepository,
    clusters: ClusterRepository,
    cluster_id: int,
    title: str,
    summary: str,
    tags: list[str],
    source: str | None,
    sources: SourceRepository | None,
    source_profile: SourceProfile | None = None,
    analytics: AnalyticsRepository | None = None,
) -> None:
    pending = editorial.get_pending_by_cluster_id(cluster_id)
    if pending is None:
        return
    try:
        score, reason, source_count = await _score_story(
            title=title,
            summary=summary,
            tags=tags,
            source=source,
            clusters=clusters,
            cluster_id=cluster_id,
            sources=sources,
            source_profile=source_profile,
            analytics=analytics,
        )
        editorial.update_priority(
            pending.id,
            priority_score=score,
            priority_reason=reason,
            source_count=source_count,
        )
    except Exception:
        logger.exception(
            "event=priority_refresh_failed cluster_id=%s pending_id=%s",
            cluster_id,
            pending.id,
        )


async def _index_entities(
    *,
    entity_repo: EntityRepository | None,
    title: str,
    summary: str,
    tags: list[str],
    pending_news_id: int | None,
    cluster_id: int | None,
    priority_score: float,
) -> None:
    if entity_repo is None:
        return
    try:
        await entity_repo.index_news_item_async(
            title=title,
            summary=summary,
            tags=tags,
            pending_news_id=pending_news_id,
            cluster_id=cluster_id,
            priority_score=priority_score,
        )
    except Exception:
        logger.exception(
            "event=entity_index_failed pending_news_id=%s cluster_id=%s",
            pending_news_id,
            cluster_id,
        )


def _media_from_item(item: NewsItem) -> MediaInfo:
    if item.media_type and item.media_type != MEDIA_NONE:
        return validate_media(
            MediaInfo(
                media_type=item.media_type,
                media_url=item.media_url,
                thumbnail_url=item.thumbnail_url,
                width=item.media_width,
                height=item.media_height,
            )
        )
    return MediaInfo.none()


async def _update_story_memory(
    *,
    story_memory: StoryMemoryService | None,
    title: str,
    summary: str | None,
    tags: list[str],
    cluster_id: int | None,
    pending_news_id: int | None,
    source: str | None,
    source_trust: float,
    source_count: int,
    cluster_variant_count: int,
    priority_score: float,
    languages: list[str] | None = None,
) -> int | None:
    if story_memory is None or cluster_id is None:
        return None
    try:
        return await story_memory.process_cluster_update(
            title=title,
            summary=summary,
            tags=tags,
            cluster_id=cluster_id,
            pending_news_id=pending_news_id,
            source=source,
            source_trust=source_trust,
            source_count=source_count,
            cluster_variant_count=cluster_variant_count,
            priority_score=priority_score,
            languages=languages,
        )
    except Exception:
        logger.exception(
            "event=story_memory_update_failed cluster_id=%s pending_news_id=%s",
            cluster_id,
            pending_news_id,
        )
        return None


async def _apply_signal_intelligence(
    *,
    signals: SignalIntelligenceService | None,
    adaptive: AdaptiveOperationsService | None,
    editorial: EditorialRepository,
    title: str,
    summary: str | None,
    tags: list[str],
    cluster_id: int | None,
    pending_news_id: int | None,
    story_id: int | None,
    source: str | None,
    source_count: int,
    cluster_variant_count: int,
    priority_score: float,
    source_profile: SourceProfile | None,
    story_importance: float = 0.5,
    story_novelty: float = 0.5,
    trend_velocity: float = 0.0,
    languages: list[str] | None = None,
) -> None:
    if signals is None:
        return
    decision = await signals.process_ingest(
        title=title,
        summary=summary,
        tags=tags,
        source=source,
        source_count=source_count,
        cluster_variants=cluster_variant_count,
        cluster_id=cluster_id,
        pending_news_id=pending_news_id,
        story_id=story_id,
        importance=story_importance,
        novelty=story_novelty,
        trend_velocity=trend_velocity,
        languages=languages,
        source_profile=source_profile,
    )
    if decision is None or pending_news_id is None:
        return
    if adaptive is not None:
        decision = adaptive.apply_policy_to_priority(
            decision,
            source_count=source_count,
            importance=story_importance,
        )
        adaptive.audit_priority_decision(
            decision,
            pending_news_id=pending_news_id,
            story_id=story_id,
            signal_id=None,
            scores={
                "importance": story_importance,
                "priority": decision.editorial_priority_score,
            },
        )
        adaptive.index_narrative_memory(
            title=title,
            summary=summary,
            entities=tags,
        )
    blended = max(priority_score, decision.editorial_priority_score)
    if decision.action == EditorialAction.SUPPRESS.value:
        blended = min(blended, 0.28)
    editorial.update_priority(
        pending_news_id,
        priority_score=blended,
        priority_reason=f"signal:{decision.reason}",
        source_count=source_count,
    )


def _funnel(stage: str, *, rejection: str | None = None) -> None:
    try:
        from bot.editorial.flow_health.funnel import record_funnel

        record_funnel(stage, rejection_reason=rejection)
    except Exception:
        pass


async def ingest_news_item(
    item: NewsItem,
    *,
    dedup: LinkDedup,
    editorial: EditorialRepository,
    clusters: ClusterRepository,
    sources: SourceRepository | None = None,
    entities: EntityRepository | None = None,
    analytics: AnalyticsRepository | None = None,
    agents: EditorialAgentService | None = None,
    localizations: LocalizationRepository | None = None,
    story_memory: StoryMemoryService | None = None,
    signal_intel: SignalIntelligenceService | None = None,
    adaptive: AdaptiveOperationsService | None = None,
) -> IngestResult:
    """
    Full editorial pipeline for a normalized news item. Never raises.
    """
    _funnel("PARSED")
    try:
        if dedup.is_seen(item.link):
            runtime_state.skipped_count += 1
            from bot.observability.metrics import record_duplicate

            record_duplicate("dedup_seen")
            _funnel("DEDUPED", rejection="link_dedup_seen")
            await _notify_operator_ingest(
                item=item,
                outcome=IngestOutcome.DUPLICATE_SKIPPED.value,
                news_id=None,
                cluster_id=None,
                priority=0.0,
                source_language=detect_language(item.title),
                confidence=0.0,
                duplicate=True,
            )
            return IngestResult(outcome=IngestOutcome.DUPLICATE_SKIPPED)

        if editorial.link_exists(item.link) or clusters.link_exists(item.link):
            runtime_state.skipped_count += 1
            logger.info("event=editorial_duplicate_skipped link=%r", item.link)
            _funnel("DEDUPED", rejection="editorial_duplicate")
            return IngestResult(outcome=IngestOutcome.DUPLICATE_SKIPPED)

        if runtime_state.dry_run_mode:
            logger.info(
                "event=dry_run_enqueue title=%r link=%r",
                item.title,
                item.link,
            )

        source_profile: SourceProfile | None = None
        if sources is not None:
            source_profile = sources.touch_source(item.source)

        story_context: dict[str, str] | None = None
        if story_memory is not None:
            preview_cluster = clusters.find_matching_cluster_id(item.title)
            if preview_cluster is not None:
                story_context = story_memory.memory_context_for_cluster(preview_cluster)
        if adaptive is not None:
            mem_block = adaptive.memory_context(item.title)
            if mem_block:
                story_context = story_context or {}
                story_context["timeline"] = (
                    story_context.get("timeline", "") + "\n" + mem_block
                ).strip()

        enriched = await _summarize_for_queue(item, story_context=story_context)
        title = str(enriched.get("title", item.title))
        summary = str(enriched.get("summary", ""))
        _funnel("SUMMARIZED")

        cluster_result = clusters.attach_story_variant(
            title=title,
            summary=summary,
            link=item.link,
            source=item.source,
        )

        if cluster_result.outcome == ClusterAttachOutcome.DUPLICATE_LINK:
            runtime_state.skipped_count += 1
            _funnel("DEDUPED", rejection="cluster_duplicate_link")
            return IngestResult(outcome=IngestOutcome.CLUSTER_DUPLICATE)

        tags = list(enriched.get("tags") or [])

        if not cluster_result.should_enqueue:
            if cluster_result.cluster_id is not None:
                await _refresh_pending_cluster_priority(
                    editorial=editorial,
                    clusters=clusters,
                    cluster_id=cluster_result.cluster_id,
                    title=title,
                    summary=summary,
                    tags=tags,
                    source=item.source,
                    sources=sources,
                    source_profile=source_profile,
                    analytics=analytics,
                )
                pending = editorial.get_pending_by_cluster_id(cluster_result.cluster_id)
                await _index_entities(
                    entity_repo=entities,
                    title=title,
                    summary=summary,
                    tags=tags,
                    pending_news_id=pending.id if pending else None,
                    cluster_id=cluster_result.cluster_id,
                    priority_score=pending.priority_score if pending else 0.5,
                )
                cluster_view = clusters.get_cluster_view(cluster_result.cluster_id)
                trust = source_profile.trust_score if source_profile else 0.5
                story_id = await _update_story_memory(
                    story_memory=story_memory,
                    title=title,
                    summary=summary,
                    tags=tags,
                    cluster_id=cluster_result.cluster_id,
                    pending_news_id=pending.id if pending else None,
                    source=item.source,
                    source_trust=trust,
                    source_count=len(cluster_view.sources) if cluster_view.sources else 1,
                    cluster_variant_count=cluster_view.variant_count,
                    priority_score=pending.priority_score if pending else 0.5,
                    languages=[detect_language(f"{title}\n{summary}")],
                )
                if pending is not None:
                    await _apply_signal_intelligence(
                        signals=signal_intel,
                        adaptive=adaptive,
                        editorial=editorial,
                        title=title,
                        summary=summary,
                        tags=tags,
                        cluster_id=cluster_result.cluster_id,
                        pending_news_id=pending.id,
                        story_id=story_id,
                        source=item.source,
                        source_count=len(cluster_view.sources) if cluster_view.sources else 1,
                        cluster_variant_count=cluster_view.variant_count,
                        priority_score=pending.priority_score,
                        source_profile=source_profile,
                        languages=[detect_language(f"{title}\n{summary}")],
                    )
            _funnel("CLUSTERED", rejection="cluster_matched_no_enqueue")
            return IngestResult(
                outcome=IngestOutcome.CLUSTER_MATCHED,
                cluster_id=cluster_result.cluster_id,
            )

        try:
            priority_score, priority_reason, source_count = await _score_story(
                title=title,
                summary=summary,
                tags=tags,
                source=item.source,
                clusters=clusters,
                cluster_id=cluster_result.cluster_id,
                sources=sources,
                source_profile=source_profile,
                analytics=analytics,
            )
        except Exception:
            logger.exception("event=priority_fallback_used link=%r", item.link)
            priority_score, priority_reason, source_count = (0.5, "default fallback", 1)

        media = _media_from_item(item)
        optimized_headline, hook_line, caption_style = await _optimize_headlines_for_story(
            title=title,
            summary=summary,
            tags=tags,
            analytics=analytics,
        )
        source_language = detect_language(f"{title}\n{summary}")
        news_id = editorial.enqueue_news(
            title=title,
            summary=summary,
            link=item.link,
            tags=tags,
            source=item.source,
            cluster_id=cluster_result.cluster_id,
            priority_score=priority_score,
            priority_reason=priority_reason,
            source_count=source_count,
            media_type=media.media_type,
            media_url=media.media_url,
            thumbnail_url=media.thumbnail_url,
            media_width=media.width,
            media_height=media.height,
            optimized_headline=optimized_headline,
            hook_line=hook_line,
            caption_style=caption_style,
            source_language=source_language,
        )
        if news_id is None:
            runtime_state.skipped_count += 1
            logger.info("event=editorial_duplicate_skipped link=%r", item.link)
            return IngestResult(outcome=IngestOutcome.DUPLICATE_SKIPPED)

        from bot.observability.metrics import record_article_ingested

        record_article_ingested(source=item.source or "unknown")
        _funnel("QUALITY_PASSED")
        logger.info(
            "event=editorial_enqueued id=%d link=%r source=%r cluster_id=%s",
            news_id,
            item.link,
            item.source,
            cluster_result.cluster_id,
        )
        await _index_entities(
            entity_repo=entities,
            title=title,
            summary=summary,
            tags=tags,
            pending_news_id=news_id,
            cluster_id=cluster_result.cluster_id,
            priority_score=priority_score,
        )
        if localizations is not None:
            await apply_localization_pipeline(
                pending_news_id=news_id,
                title=title,
                summary=summary,
                hook_line=hook_line,
                editorial=editorial,
                localizations=localizations,
            )
        if agents is not None:
            try:
                await agents.process_new_pending(news_id)
            except Exception:
                logger.exception(
                    "event=agent_action_failed action=process_new_pending id=%d",
                    news_id,
                )
        cluster_view = clusters.get_cluster_view(cluster_result.cluster_id)
        trust = source_profile.trust_score if source_profile else 0.5
        story_id = await _update_story_memory(
            story_memory=story_memory,
            title=title,
            summary=summary,
            tags=tags,
            cluster_id=cluster_result.cluster_id,
            pending_news_id=news_id,
            source=item.source,
            source_trust=trust,
            source_count=source_count,
            cluster_variant_count=cluster_view.variant_count,
            priority_score=priority_score,
            languages=[source_language],
        )
        await _apply_signal_intelligence(
            signals=signal_intel,
            adaptive=adaptive,
            editorial=editorial,
            title=title,
            summary=summary,
            tags=tags,
            cluster_id=cluster_result.cluster_id,
            pending_news_id=news_id,
            story_id=story_id,
            source=item.source,
            source_count=source_count,
            cluster_variant_count=cluster_view.variant_count,
            priority_score=priority_score,
            source_profile=source_profile,
            languages=[source_language],
        )
        await _notify_operator_ingest(
            item=item,
            outcome=IngestOutcome.ENQUEUED.value,
            news_id=news_id,
            cluster_id=cluster_result.cluster_id,
            priority=priority_score,
            source_language=source_language,
            confidence=assessment_confidence(priority_score),
        )
        return IngestResult(
            outcome=IngestOutcome.ENQUEUED,
            news_id=news_id,
            cluster_id=cluster_result.cluster_id,
        )
    except Exception:
        logger.exception("event=ingest_item_failed link=%r", item.link)
        return IngestResult(outcome=IngestOutcome.DUPLICATE_SKIPPED)


def assessment_confidence(priority: float) -> float:
    return max(0.35, min(0.98, 0.45 + priority * 0.5))


async def _notify_operator_ingest(
    *,
    item: NewsItem,
    outcome: str,
    news_id: int | None,
    cluster_id: int | None,
    priority: float,
    source_language: str,
    confidence: float,
    duplicate: bool = False,
) -> None:
    try:
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is None:
            return
        await console.notify_ingest(
            source=item.source or "unknown",
            language=source_language,
            headline=item.title,
            outcome=outcome,
            confidence=confidence,
            cluster_id=cluster_id,
            news_id=news_id,
            priority=priority,
            duplicate=duplicate,
        )
        if (
            console.settings.telegram_live_approval_cards
            and news_id
            and priority >= 0.68
            and outcome == IngestOutcome.ENQUEUED.value
        ):
            await console.send_approval_card(
                news_id=news_id,
                headline=item.title,
                summary=item.summary or item.title,
                confidence=confidence,
                epistemic_stability=0.75,
                contradiction_exposure=0,
                misinfo_risk=0.1,
                source_diversity=1,
                priority=priority,
                replay_id=f"evt_{news_id}",
            )
    except Exception:
        logger.debug("event=operator_ingest_notify_skipped", exc_info=True)
