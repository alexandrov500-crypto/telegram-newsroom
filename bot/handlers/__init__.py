from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from functools import wraps
from typing import Any, TypeVar

from aiogram import BaseMiddleware, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, TelegramObject

from bot.editorial.formatting import (
    format_pending_queue_item,
)
from bot.processing.entities import extract_entities
from bot.processing.headlines import (
    CAPTION_HYBRID,
    CAPTION_OPTIMIZED,
    CAPTION_ORIGINAL,
    optimize_story_headlines,
    resolve_publish_headline,
    resolve_publish_hook,
)
from bot.config import BotSettings, telethon_configured
from bot.editorial.agent_service import EditorialAgentService
from bot.editorial.story_formatting import (
    format_lifecycle_summary,
    format_story_detail,
    format_story_list,
)
from bot.editorial.story_memory import StoryMemoryService
from bot.signals.signal_formatting import (
    format_anomaly_list,
    format_credibility_list,
    format_forecast_list,
    format_signal_list,
)
from bot.signals.signal_service import SignalIntelligenceService
from bot.adaptive.service import AdaptiveOperationsService
from bot.adaptive.policies import OperationalMode
from bot.editorial.publish_flow import publish_pending_item
from bot.processing.languages import LANGUAGE_LABELS, SUPPORTED_LANGUAGES, normalize_language_code
from bot.publisher import ChannelPublisher
from bot.publishing.channel_router import ChannelRouter
from bot.storage.agent_repository import AgentRepository
from bot.storage.localization_repository import LocalizationRepository
from bot.runtime.auth import is_admin
from bot.runtime.state import runtime_state
from bot.digest.service import DigestService
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.digest_repository import DIGEST_HOURLY, DIGEST_MORNING
from bot.storage.editorial_repository import EditorialRepository, PendingNewsItem
from bot.storage.repository import LinkDedup
from bot.storage.entity_repository import EntityRepository
from bot.storage.source_repository import SourceRepository

logger = logging.getLogger(__name__)

router = Router(name="bootstrap")

_Handler = TypeVar("_Handler", bound=Callable[..., Awaitable[Any]])


class IncomingMessageLogMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            text_preview = (event.text or event.caption or "")[:120]
            logger.info(
                "Incoming message user_id=%s username=%s chat_id=%s text=%r",
                event.from_user.id,
                event.from_user.username,
                event.chat.id if event.chat else None,
                text_preview,
            )
        return await handler(event, data)


def _log_runtime_command(message: Message, command: str) -> None:
    user = message.from_user
    logger.info(
        "event=runtime_command command=%s user_id=%s username=%s",
        command,
        user.id if user else None,
        user.username if user else None,
    )


def admin_only(command: str) -> Callable[[_Handler], _Handler]:
    def decorator(handler: _Handler) -> _Handler:
        @wraps(handler)
        async def wrapper(message: Message, *args: Any, **kwargs: Any) -> Any:
            user = message.from_user
            if not await is_admin(message):
                logger.warning(
                    "event=admin_access_denied user_id=%s username=%s command=%s",
                    user.id if user else None,
                    user.username if user else None,
                    command,
                )
                await message.answer("Unauthorized")
                return None
            _log_runtime_command(message, command)
            try:
                return await handler(message, *args, **kwargs)
            except Exception:
                logger.exception(
                    "event=runtime_command_failed command=%s user_id=%s",
                    command,
                    user.id if user else None,
                )
                await message.answer("Command failed.")
                return None

        return wrapper  # type: ignore[return-value]

    return decorator


def _format_runtime_status() -> str:
    uptime_minutes = int(
        (datetime.now(timezone.utc) - runtime_state.startup_time).total_seconds() // 60
    )
    return (
        "Newsroom Runtime Status\n\n"
        f"ingestion_paused={str(runtime_state.ingestion_paused).lower()}\n"
        f"dry_run_mode={str(runtime_state.dry_run_mode).lower()}\n"
        f"published_count={runtime_state.published_count}\n"
        f"skipped_count={runtime_state.skipped_count}\n"
        f"failed_count={runtime_state.failed_count}\n"
        f"uptime_minutes={uptime_minutes}\n"
        f"enabled_languages={','.join(sorted(runtime_state.enabled_languages))}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    user_id = user.id if user else None
    username = user.username if user else None
    logger.info("/start from user_id=%s username=%s", user_id, username)
    await message.answer("Bot is alive ✅")


def _publish_response(
    *,
    success: bool,
    channel_id: int | None,
    error: str | None = None,
) -> str:
    return json.dumps(
        {
            "success": success,
            "channel_id": channel_id,
            "error": error,
        },
        ensure_ascii=False,
    )


def _parse_command_id(message: Message, command: str) -> int | None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        return None
    return int(parts[1].strip())


def _format_pending_news_list(
    items: list[PendingNewsItem],
    *,
    cluster_repo: ClusterRepository | None = None,
    entity_repo: EntityRepository | None = None,
) -> str:
    if not items:
        return "No pending news items."

    cluster_views: dict[int, tuple[tuple[str, ...], int]] = {}
    if cluster_repo is not None:
        for item in items:
            if item.cluster_id is not None and item.cluster_id not in cluster_views:
                view = cluster_repo.get_cluster_view(item.cluster_id)
                cluster_views[item.cluster_id] = (view.sources, view.variant_count)

    blocks: list[str] = []
    for item in items:
        sources = item.sources
        variant_count = item.variant_count
        if item.cluster_id is not None and item.cluster_id in cluster_views:
            sources, variant_count = cluster_views[item.cluster_id]
        entity_names: tuple[str, ...] = ()
        if entity_repo is not None:
            entity_names = tuple(entity_repo.get_entity_names_for_pending(item.id))
        blocks.append(
            format_pending_queue_item(
                news_id=item.id,
                title=item.title,
                tags=item.tags,
                sources=sources,
                variant_count=variant_count,
                priority_score=item.priority_score,
                priority_reason=item.priority_reason,
                media_type=item.media_type,
                entity_names=entity_names,
                optimized_headline=item.optimized_headline,
                hook_line=item.hook_line,
            )
        )
    return "\n\n".join(blocks)


def _format_digest_run_result(result) -> str:
    if result.skipped_empty:
        return f"{result.digest_type} digest skipped: no eligible published stories."
    if result.error and not result.published:
        return (
            f"Digest #{result.digest_id} generated ({result.item_count} items) "
            f"but publish failed: {result.error}"
        )
    if result.published:
        return (
            f"Digest #{result.digest_id} published ({result.digest_type}, "
            f"{result.item_count} items)."
        )
    return (
        f"Digest #{result.digest_id} generated ({result.digest_type}, "
        f"{result.item_count} items, not published)."
    )


def _format_source_profile(profile) -> str:
    return (
        f"Source: {profile.source_name}\n"
        f"type={profile.source_type}\n"
        f"trust_score={profile.trust_score:.3f}\n"
        f"approval_ratio={profile.approval_ratio:.2f}\n"
        f"articles={profile.article_count}\n"
        f"accepted={profile.accepted_count}\n"
        f"rejected={profile.rejected_count}"
    )


def _format_telegram_status(settings: BotSettings) -> str:
    channels = ", ".join(settings.telegram_source_channels) or "(none)"
    last_cycle = (
        runtime_state.telegram_last_cycle_at.isoformat()
        if runtime_state.telegram_last_cycle_at
        else "never"
    )
    return (
        "Telegram Ingestion Status\n\n"
        f"configured={str(telethon_configured(settings)).lower()}\n"
        f"connected={str(runtime_state.telegram_connected).lower()}\n"
        f"sources={channels}\n"
        f"session={settings.telegram_session_name}\n"
        f"last_cycle={last_cycle}\n"
        f"last_error={runtime_state.telegram_last_error or 'none'}\n"
        f"messages_ingested={runtime_state.telegram_messages_ingested}\n"
        f"auto_approval={str(runtime_state.auto_approval_enabled).lower()}"
    )


def register_handlers(
    dp: Dispatcher,
    *,
    publisher: ChannelPublisher,
    editorial: EditorialRepository,
    clusters: ClusterRepository,
    digest_service: DigestService,
    link_dedup: LinkDedup,
    settings: BotSettings,
    sources: SourceRepository | None,
    entities: EntityRepository | None,
    analytics: AnalyticsRepository | None,
    agents: EditorialAgentService | None = None,
    agent_repo: AgentRepository | None = None,
    channel_router: ChannelRouter | None = None,
    localizations: LocalizationRepository | None = None,
    story_memory: StoryMemoryService | None = None,
    signal_intel: SignalIntelligenceService | None = None,
    adaptive: AdaptiveOperationsService | None = None,
    publish_idempotency: object | None = None,
    node_id: str = "local",
) -> None:
    router.message.middleware(IncomingMessageLogMiddleware())

    @router.message(Command("test_publish"))
    async def cmd_test_publish(message: Message) -> None:
        user = message.from_user
        logger.info(
            "/test_publish from user_id=%s username=%s",
            user.id if user else None,
            user.username if user else None,
        )

        if not publisher.channel_configured:
            logger.warning("event=publish_failed reason=channel_not_configured")
            await message.answer("Channel not configured")
            return

        logger.info(
            "event=publish_attempt channel_id=%s",
            publisher.channel_id,
        )
        result = await publisher.send_to_channel("Test message from newsroom bot")

        payload = _publish_response(
            success=result.success,
            channel_id=result.channel_id,
            error=result.error,
        )

        if result.success:
            logger.info(
                "event=publish_success channel_id=%s duration_ms=%s",
                result.channel_id,
                result.duration_ms,
            )
        else:
            logger.warning(
                "event=publish_failed channel_id=%s error=%s",
                result.channel_id,
                result.error,
            )

        await message.answer(payload)

    @router.message(Command("pause_ingestion"))
    @admin_only("/pause_ingestion")
    async def cmd_pause_ingestion(message: Message) -> None:
        runtime_state.ingestion_paused = True
        logger.info("event=ingestion_paused")
        await message.answer("Ingestion paused.")

    @router.message(Command("resume_ingestion"))
    @admin_only("/resume_ingestion")
    async def cmd_resume_ingestion(message: Message) -> None:
        runtime_state.ingestion_paused = False
        logger.info("event=ingestion_resumed")
        await message.answer("Ingestion resumed.")

    @router.message(Command("enable_dry_run"))
    @admin_only("/enable_dry_run")
    async def cmd_enable_dry_run(message: Message) -> None:
        runtime_state.dry_run_mode = True
        logger.info("event=dry_run_enabled")
        await message.answer("Dry-run mode enabled (no channel publishes).")

    @router.message(Command("disable_dry_run"))
    @admin_only("/disable_dry_run")
    async def cmd_disable_dry_run(message: Message) -> None:
        runtime_state.dry_run_mode = False
        logger.info("event=dry_run_disabled")
        await message.answer("Dry-run mode disabled.")

    @router.message(Command("runtime_status"))
    @admin_only("/runtime_status")
    async def cmd_runtime_status(message: Message) -> None:
        await message.answer(_format_runtime_status())

    @router.message(Command("pending_news"))
    @admin_only("/pending_news")
    async def cmd_pending_news(message: Message) -> None:
        items = editorial.get_pending_news(limit=10)
        await message.answer(
            _format_pending_news_list(
                items,
                cluster_repo=clusters,
                entity_repo=entities,
            )
        )

    @router.message(Command("approve"))
    @admin_only("/approve")
    async def cmd_approve(message: Message) -> None:
        news_id = _parse_command_id(message, "/approve")
        if news_id is None:
            await message.answer("Usage: /approve <id>")
            return

        item = editorial.approve_news(news_id)
        if item is None:
            await message.answer(f"Item #{news_id} not found or not pending.")
            return

        if runtime_state.dry_run_mode:
            logger.info(
                "event=editorial_approved dry_run=true id=%d link=%r",
                news_id,
                item.link,
            )
            await message.answer(
                f"Dry-run: would publish #{news_id} (not sent to channel)."
            )
            return

        channels_ready = publisher.channel_configured or (
            channel_router is not None and bool(channel_router.configured_languages())
        )
        if not channels_ready:
            logger.warning(
                "event=editorial_publish_failed id=%d reason=channel_not_configured",
                news_id,
            )
            await message.answer("Channel not configured.")
            return

        if adaptive is not None:
            adaptive.control_plane.feedback.record_admin_override(
                pending_news_id=news_id,
                action="approve",
            )
        from bot.staging.context import get_publish_guard

        flow = await publish_pending_item(
            item,
            publisher=publisher,
            editorial=editorial,
            link_dedup=link_dedup,
            sources=sources,
            entities=entities,
            analytics=analytics,
            channel_router=channel_router,
            localizations=localizations,
            adaptive=adaptive,
            idempotency=publish_idempotency,
            node_id=node_id,
            operator_approved=True,
            publish_guard=get_publish_guard(),
        )
        if not flow.success:
            runtime_state.failed_count += 1
            logger.warning(
                "event=editorial_publish_failed id=%d link=%r error=%r",
                news_id,
                item.link,
                flow.error,
            )
            await message.answer(
                f"Publish failed for #{news_id}. Item remains pending."
            )
            return

        logger.info(
            "event=editorial_approved id=%d link=%r",
            news_id,
            item.link,
        )
        await message.answer(f"Approved and published: #{news_id}")

    @router.message(Command("reject"))
    @admin_only("/reject")
    async def cmd_reject(message: Message) -> None:
        news_id = _parse_command_id(message, "/reject")
        if news_id is None:
            await message.answer("Usage: /reject <id>")
            return

        pending_item = editorial.get_by_id(news_id)
        if not editorial.reject_news(news_id):
            await message.answer(f"Item #{news_id} not found or not pending.")
            return

        if sources is not None and pending_item is not None:
            sources.record_rejection(pending_item.source)

        if agent_repo is not None and agent_repo.reverse_latest_auto_approval(news_id):
            logger.info("event=agent_decision_reversed pending_news_id=%d", news_id)

        logger.info("event=editorial_rejected id=%d", news_id)
        await message.answer(f"Rejected: #{news_id}")

    async def _run_manual_digest(message: Message, digest_type: str, command: str) -> None:
        result = await digest_service.run_digest(digest_type)
        await message.answer(_format_digest_run_result(result))

    @router.message(Command("generate_digest"))
    @admin_only("/generate_digest")
    async def cmd_generate_digest(message: Message) -> None:
        await _run_manual_digest(message, DIGEST_HOURLY, "/generate_digest")

    @router.message(Command("manual_hourly_digest"))
    @admin_only("/manual_hourly_digest")
    async def cmd_manual_hourly_digest(message: Message) -> None:
        await _run_manual_digest(message, DIGEST_HOURLY, "/manual_hourly_digest")

    @router.message(Command("manual_morning_digest"))
    @admin_only("/manual_morning_digest")
    async def cmd_manual_morning_digest(message: Message) -> None:
        await _run_manual_digest(message, DIGEST_MORNING, "/manual_morning_digest")

    @router.message(Command("telegram_sources"))
    @admin_only("/telegram_sources")
    async def cmd_telegram_sources(message: Message) -> None:
        if not settings.telegram_source_channels:
            await message.answer("No TELEGRAM_SOURCE_CHANNELS configured.")
            return
        lines = ["Telegram source channels:", ""]
        lines.extend(f"- {channel}" for channel in settings.telegram_source_channels)
        await message.answer("\n".join(lines))

    @router.message(Command("show_telegram_status"))
    @admin_only("/show_telegram_status")
    async def cmd_show_telegram_status(message: Message) -> None:
        await message.answer(_format_telegram_status(settings))

    @router.message(Command("top_sources"))
    @admin_only("/top_sources")
    async def cmd_top_sources(message: Message) -> None:
        if sources is None:
            await message.answer("Source reputation store unavailable.")
            return
        rows = sources.top_sources(limit=10)
        if not rows:
            await message.answer("No sources tracked yet.")
            return
        lines = ["Top sources by trust:", ""]
        for index, profile in enumerate(rows, start=1):
            lines.append(
                f"{index}. {profile.source_name} "
                f"[{profile.trust_score:.2f}] "
                f"ratio={profile.approval_ratio:.2f} "
                f"articles={profile.article_count}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("source_stats"))
    @admin_only("/source_stats")
    async def cmd_source_stats(message: Message) -> None:
        if sources is None:
            await message.answer("Source reputation store unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /source_stats <source_name>")
            return
        profile = sources.get_source(parts[1].strip())
        if profile is None:
            await message.answer(f"Source not found: {parts[1].strip()}")
            return
        await message.answer(_format_source_profile(profile))

    @router.message(Command("trending_entities"))
    @admin_only("/trending_entities")
    async def cmd_trending_entities(message: Message) -> None:
        if entities is None:
            await message.answer("Entity intelligence unavailable.")
            return
        rows = entities.get_trending_entities(limit=10)
        if not rows:
            await message.answer("No trending entities yet.")
            return
        lines = ["Trending entities:", ""]
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. {row.entity_name} ({row.entity_type}) "
                f"mentions={row.mention_count} recent={row.recent_mentions} "
                f"avg_priority={row.avg_priority:.2f}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("entity_news"))
    @admin_only("/entity_news")
    async def cmd_entity_news(message: Message) -> None:
        if entities is None:
            await message.answer("Entity intelligence unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /entity_news <entity_name>")
            return
        entity, news = entities.get_entity_news(parts[1].strip(), limit=8)
        if entity is None:
            await message.answer(f"Entity not found: {parts[1].strip()}")
            return
        lines = [
            f"Entity: {entity.entity_name} ({entity.entity_type})",
            f"mentions={entity.mention_count}",
            "",
            "Related stories:",
        ]
        if not news:
            lines.append("(no linked stories yet)")
        for item in news:
            lines.append(
                f"- [{item.priority_score:.2f}] #{item.pending_news_id} {item.title[:80]}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("top_topics"))
    @admin_only("/top_topics")
    async def cmd_top_topics(message: Message) -> None:
        if entities is None:
            await message.answer("Entity intelligence unavailable.")
            return
        topics = entities.get_top_topics(limit=10)
        if not topics:
            await message.answer("No topics tracked yet.")
            return
        lines = ["Top topics:", ""]
        for index, topic in enumerate(topics, start=1):
            lines.append(
                f"{index}. {topic.topic_name} "
                f"mentions={topic.mention_count} avg_priority={topic.avg_priority:.2f}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("rewrite_headline"))
    @admin_only("/rewrite_headline")
    async def cmd_rewrite_headline(message: Message) -> None:
        news_id = _parse_command_id(message, "/rewrite_headline")
        if news_id is None:
            await message.answer("Usage: /rewrite_headline <id>")
            return
        item = editorial.get_by_id(news_id)
        if item is None or item.status != "pending":
            await message.answer(f"Item #{news_id} not found or not pending.")
            return

        entity_names: list[str] = []
        if entities is not None:
            entity_names = entities.get_entity_names_for_pending(news_id)

        try:
            headline_pkg = await optimize_story_headlines(
                title=item.title,
                summary=item.summary or item.title,
                tags=item.tags,
                entities=entity_names,
                mode=runtime_state.headline_mode,
                use_llm=runtime_state.ai_headlines_enabled,
            )
            editorial.update_headlines(
                news_id,
                optimized_headline=headline_pkg.optimized_headline,
                hook_line=headline_pkg.hook_line,
            )
            lines = [
                f"Rewrote headline for #{news_id}:",
                f"Optimized: {headline_pkg.optimized_headline}",
            ]
            if headline_pkg.hook_line:
                lines.append(f"Hook: {headline_pkg.hook_line}")
            await message.answer("\n".join(lines))
        except Exception:
            logger.exception("event=headline_fallback_used reason=rewrite_command id=%d", news_id)
            await message.answer(f"Headline rewrite failed for #{news_id}; original kept.")

    @router.message(Command("toggle_ai_headlines"))
    @admin_only("/toggle_ai_headlines")
    async def cmd_toggle_ai_headlines(message: Message) -> None:
        runtime_state.ai_headlines_enabled = not runtime_state.ai_headlines_enabled
        state = "enabled" if runtime_state.ai_headlines_enabled else "disabled"
        logger.info("event=caption_style_changed ai_headlines=%s", state)
        await message.answer(f"AI headlines {state}.")

    @router.message(Command("show_caption_style"))
    @admin_only("/show_caption_style")
    async def cmd_show_caption_style(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            style = parts[1].strip().lower()
            if style in (CAPTION_ORIGINAL, CAPTION_OPTIMIZED, CAPTION_HYBRID):
                runtime_state.caption_style = style
                logger.info("event=caption_style_changed style=%s", style)
                await message.answer(f"Caption style set to: {style}")
                return
            await message.answer(
                "Unknown style. Use: original, optimized, or hybrid.\n"
                "Example: /show_caption_style optimized"
            )
            return
        await message.answer(
            "Caption settings:\n"
            f"ai_headlines={str(runtime_state.ai_headlines_enabled).lower()}\n"
            f"caption_style={runtime_state.caption_style}\n"
            f"headline_mode={runtime_state.headline_mode}\n\n"
            "Set style: /show_caption_style <original|optimized|hybrid>"
        )

    @router.message(Command("top_posts"))
    @admin_only("/top_posts")
    async def cmd_top_posts(message: Message) -> None:
        if analytics is None:
            await message.answer("Analytics unavailable.")
            return
        posts = analytics.get_top_posts(limit=10)
        if not posts:
            await message.answer("No analytics collected yet.")
            return
        lines = ["Top posts:", ""]
        for index, post in enumerate(posts, start=1):
            title = (post.headline or "Untitled")[:80]
            lines.append(
                f"{index}. [{post.engagement_score:.2f}] {title} "
                f"(views={post.views}, forwards={post.forwards})"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("analytics_summary"))
    @admin_only("/analytics_summary")
    async def cmd_analytics_summary(message: Message) -> None:
        if analytics is None:
            await message.answer("Analytics unavailable.")
            return
        summary = analytics.analytics_summary()
        await message.answer(
            "Analytics summary (7d):\n\n"
            f"posts={summary['post_count']}\n"
            f"avg_engagement={summary['avg_engagement']:.3f}\n"
            f"max_engagement={summary['max_engagement']:.3f}\n"
            f"total_views={summary['total_views']}"
        )

    @router.message(Command("top_entities_engagement"))
    @admin_only("/top_entities_engagement")
    async def cmd_top_entities_engagement(message: Message) -> None:
        if analytics is None:
            await message.answer("Analytics unavailable.")
            return
        rows = analytics.get_top_entities_by_engagement(limit=10)
        if not rows:
            await message.answer("No entity engagement data yet.")
            return
        lines = ["Top entities by engagement:", ""]
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. {row.signal_key} "
                f"score={row.avg_engagement:.3f} samples={row.sample_count}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("top_headline_patterns"))
    @admin_only("/top_headline_patterns")
    async def cmd_top_headline_patterns(message: Message) -> None:
        if analytics is None:
            await message.answer("Analytics unavailable.")
            return
        patterns = analytics.get_best_headline_patterns(limit=10)
        hooks = analytics.get_top_signals("hook", limit=5)
        if not patterns and not hooks:
            await message.answer("No headline pattern data yet.")
            return
        lines = ["Top headline patterns:", ""]
        for index, row in enumerate(patterns, start=1):
            lines.append(
                f"{index}. \"{row.signal_key}\" "
                f"score={row.avg_engagement:.3f} n={row.sample_count}"
            )
        if hooks:
            lines.extend(["", "Top hooks:"])
            for row in hooks:
                lines.append(f"- {row.signal_key} score={row.avg_engagement:.3f}")
        await message.answer("\n".join(lines))

    @router.message(Command("agent_status"))
    @admin_only("/agent_status")
    async def cmd_agent_status(message: Message) -> None:
        enabled = runtime_state.auto_approval_enabled
        service_ok = agents is not None
        recent_count = 0
        if agent_repo is not None:
            recent_count = len(agent_repo.recent_actions(limit=50))
        await message.answer(
            "Editorial agents:\n\n"
            f"service={'ready' if service_ok else 'unavailable'}\n"
            f"auto_approval_enabled={str(enabled).lower()}\n"
            f"audit_actions_recorded={recent_count}\n\n"
            "Toggle: /toggle_auto_approval\n"
            "Recent: /recent_agent_actions"
        )

    @router.message(Command("recent_agent_actions"))
    @admin_only("/recent_agent_actions")
    async def cmd_recent_agent_actions(message: Message) -> None:
        if agent_repo is None:
            await message.answer("Agent audit store unavailable.")
            return
        actions = agent_repo.recent_actions(limit=15)
        if not actions:
            await message.answer("No agent actions recorded yet.")
            return
        lines = ["Recent agent actions:", ""]
        for row in actions:
            reversed_flag = " [reversed]" if row.reversed_at else ""
            lines.append(
                f"#{row.id} news={row.pending_news_id} "
                f"type={row.action_type}{reversed_flag}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("toggle_auto_approval"))
    @admin_only("/toggle_auto_approval")
    async def cmd_toggle_auto_approval(message: Message) -> None:
        runtime_state.auto_approval_enabled = not runtime_state.auto_approval_enabled
        state = "enabled" if runtime_state.auto_approval_enabled else "disabled"
        logger.info("event=auto_approval_toggled enabled=%s", runtime_state.auto_approval_enabled)
        await message.answer(f"Auto-approval {state}.")

    @router.message(Command("review_risk"))
    @admin_only("/review_risk")
    async def cmd_review_risk(message: Message) -> None:
        news_id = _parse_command_id(message, "/review_risk")
        if news_id is None:
            await message.answer("Usage: /review_risk <id>")
            return
        if agent_repo is None:
            await message.answer("Agent audit store unavailable.")
            return
        record = agent_repo.get_latest_risk_assessment(news_id)
        if record is None:
            if agents is not None:
                assessment = await agents.evaluate_pending(news_id)
                if assessment is not None:
                    record = agent_repo.get_latest_risk_assessment(news_id)
            if record is None:
                await message.answer(f"No risk assessment for #{news_id}.")
                return
        factors = record.factors_json or "[]"
        blocked = record.blocked_categories_json or "[]"
        await message.answer(
            f"Risk review #{news_id}:\n\n"
            f"risk_score={record.risk_score:.3f}\n"
            f"confidence={record.confidence_score:.3f}\n"
            f"human_review={str(record.requires_human_review).lower()}\n"
            f"factors={factors}\n"
            f"blocked={blocked}\n"
            f"assessed_at={record.created_at}"
        )

    @router.message(Command("supported_languages"))
    @admin_only("/supported_languages")
    async def cmd_supported_languages(message: Message) -> None:
        lines = ["Supported languages:", ""]
        for code in SUPPORTED_LANGUAGES:
            enabled = code in runtime_state.enabled_languages
            label = LANGUAGE_LABELS.get(code, code)
            channel = (
                channel_router.channel_for(code)
                if channel_router is not None
                else publisher.channel_id
            )
            lines.append(
                f"- {code} ({label}) enabled={str(enabled).lower()} "
                f"channel={'yes' if channel else 'no'}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("language_status"))
    @admin_only("/language_status")
    async def cmd_language_status(message: Message) -> None:
        enabled = ", ".join(sorted(runtime_state.enabled_languages)) or "(none)"
        configured = (
            ", ".join(channel_router.configured_languages())
            if channel_router is not None
            else "default"
        )
        await message.answer(
            "Language status:\n\n"
            f"enabled={enabled}\n"
            f"channels_configured={configured}\n\n"
            "Toggle: /toggle_language <code>"
        )

    @router.message(Command("toggle_language"))
    @admin_only("/toggle_language")
    async def cmd_toggle_language(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /toggle_language <ru|en>")
            return
        lang = normalize_language_code(parts[1].strip())
        if lang is None:
            await message.answer("Unsupported language code.")
            return
        now_enabled = runtime_state.toggle_language(lang)
        state = "enabled" if now_enabled else "disabled"
        await message.answer(f"Language {lang} {state}.")

    @router.message(Command("show_localized_story"))
    @admin_only("/show_localized_story")
    async def cmd_show_localized_story(message: Message) -> None:
        news_id = _parse_command_id(message, "/show_localized_story")
        if news_id is None:
            await message.answer("Usage: /show_localized_story <id>")
            return
        item = editorial.get_by_id(news_id)
        if item is None:
            await message.answer(f"Item #{news_id} not found.")
            return
        lines = [
            f"Story #{news_id}",
            f"source_language={item.source_language}",
            f"title={item.title[:120]}",
            "",
        ]
        if localizations is not None:
            for loc in localizations.list_for_pending(news_id):
                lines.extend(
                    [
                        f"[{loc.language}]",
                        f"headline={loc.localized_headline or loc.translated_title}",
                        f"hook={loc.localized_hook or '-'}",
                        "",
                    ]
                )
        else:
            lines.append("Localization store unavailable.")
        await message.answer("\n".join(lines).strip())

    @router.message(Command("low_trust_sources"))
    @admin_only("/low_trust_sources")
    async def cmd_low_trust_sources(message: Message) -> None:
        if sources is None:
            await message.answer("Source reputation store unavailable.")
            return
        rows = sources.low_trust_sources(limit=10)
        if not rows:
            await message.answer("No low-trust sources recorded.")
            return
        lines = ["Low-trust sources:", ""]
        for profile in rows:
            lines.append(
                f"- {profile.source_name} "
                f"[{profile.trust_score:.2f}] "
                f"ratio={profile.approval_ratio:.2f}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("stories"))
    @admin_only("/stories")
    async def cmd_stories(message: Message) -> None:
        if story_memory is None:
            await message.answer("Story memory unavailable.")
            return
        _log_runtime_command(message, "/stories")
        stories = story_memory.registry.active_stories(limit=40)
        text = format_story_list(stories, title="Active stories")
        await message.answer(text[:3900])

    @router.message(Command("story"))
    @admin_only("/story")
    async def cmd_story(message: Message) -> None:
        if story_memory is None:
            await message.answer("Story memory unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await message.answer("Usage: /story <id>")
            return
        story_id = int(parts[1].strip())
        story = story_memory.registry.get(story_id)
        if story is None:
            await message.answer(f"Story #{story_id} not found.")
            return
        timeline = story_memory.registry.timeline(story_id, limit=12)
        await message.answer(format_story_detail(story, timeline=timeline)[:3900])

    @router.message(Command("trending"))
    @admin_only("/trending")
    async def cmd_trending_stories(message: Message) -> None:
        if story_memory is None:
            await message.answer("Story memory unavailable.")
            return
        stories = story_memory.registry.trending(limit=10)
        text = format_story_list(stories, title="Trending narratives")
        await message.answer(text[:3900])

    @router.message(Command("top"))
    @admin_only("/top")
    async def cmd_top_stories(message: Message) -> None:
        if story_memory is None:
            await message.answer("Story memory unavailable.")
            return
        stories = story_memory.registry.top_stories(limit=10)
        text = format_story_list(stories, title="Top stories by importance")
        await message.answer(text[:3900])

    @router.message(Command("narrative"))
    @admin_only("/narrative")
    async def cmd_narrative(message: Message) -> None:
        if story_memory is None:
            await message.answer("Story memory unavailable.")
            return
        counts = story_memory.registry.lifecycle_counts()
        archived = story_memory.maintenance_pass()
        text = format_lifecycle_summary(counts)
        if archived:
            text += f"\n\nArchived {archived} stale stories."
        await message.answer(text[:3900])

    @router.message(Command("timeline"))
    @admin_only("/timeline")
    async def cmd_timeline(message: Message) -> None:
        if story_memory is None:
            await message.answer("Story memory unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await message.answer("Usage: /timeline <story_id>")
            return
        story_id = int(parts[1].strip())
        story = story_memory.registry.get(story_id)
        if story is None:
            await message.answer(f"Story #{story_id} not found.")
            return
        timeline = story_memory.registry.timeline(story_id, limit=15)
        await message.answer(format_story_detail(story, timeline=timeline)[:3900])

    @router.message(Command("signals"))
    @admin_only("/signals")
    async def cmd_signals(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        rows = signal_intel.repository.list_recent_signals(limit=12)
        await message.answer(format_signal_list(rows, title="Live signals")[:3900])

    @router.message(Command("anomalies"))
    @admin_only("/anomalies")
    async def cmd_anomalies(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        rows = signal_intel.repository.list_recent_anomalies(limit=12)
        await message.answer(format_anomaly_list(rows)[:3900])

    @router.message(Command("forecast"))
    @admin_only("/forecast")
    async def cmd_forecast(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        rows = signal_intel.repository.list_forecasts(limit=10)
        await message.answer(format_forecast_list(rows)[:3900])

    @router.message(Command("impact"))
    @admin_only("/impact")
    async def cmd_impact(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        rows = signal_intel.repository.list_recent_signals(limit=8)
        lines = ["High-impact signals:", ""]
        for row in sorted(rows, key=lambda r: -(r.priority_score or 0)):
            lines.append(
                f"- #{row.id} {_esc_impact(row.title)} "
                f"pri={row.priority_score or 0:.2f} type={row.signal_type}"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("credibility"))
    @admin_only("/credibility")
    async def cmd_credibility(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        rows = signal_intel.repository.list_credibility(limit=12)
        await message.answer(format_credibility_list(rows)[:3900])

    @router.message(Command("escalations"))
    @admin_only("/escalations")
    async def cmd_escalations(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        forecasts = signal_intel.repository.list_forecasts(limit=15)
        hot = [f for f in forecasts if float(f.get("forecast_probability", 0)) >= 0.65]
        await message.answer(format_forecast_list(hot)[:3900])

    @router.message(Command("market"))
    @admin_only("/market")
    async def cmd_market_signals(message: Message) -> None:
        if signal_intel is None:
            await message.answer("Signal intelligence unavailable.")
            return
        rows = signal_intel.repository.list_recent_signals(
            limit=10,
            signal_type="market_moving",
        )
        await message.answer(
            format_signal_list(rows, title="Market-moving signals")[:3900],
        )

    @router.message(Command("policy"))
    @admin_only("/policy")
    async def cmd_policy(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        policy = adaptive.active_policy()
        lines = [
            f"Policy: {policy.name}",
            f"Mode: {policy.mode}",
            f"escalation_threshold={policy.escalation_threshold}",
            f"auto_publish_threshold={policy.auto_publish_threshold}",
            f"anomaly_z={policy.anomaly_z_threshold}",
            f"suppress_below={policy.suppress_below}",
            f"max_daily_ai_cost_usd={policy.max_daily_ai_cost_usd}",
            f"multi_source={policy.require_multi_source_confirmation}",
        ]
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("mode"))
    @admin_only("/mode")
    async def cmd_mode(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            modes = adaptive.control_plane.list_modes()
            await message.answer(
                "Usage: /mode <name>\n\nModes:\n" + "\n".join(f"- {m}" for m in modes),
            )
            return
        mode = parts[1].strip().lower()
        if mode not in {m.value for m in OperationalMode}:
            await message.answer(f"Unknown mode: {mode}")
            return
        policy = adaptive.control_plane.set_mode(mode)
        await message.answer(f"Mode set to {policy.mode} ({policy.name})")

    @router.message(Command("costs"))
    @admin_only("/costs")
    async def cmd_costs(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        summary = adaptive.control_plane.daily_cost_summary()
        await message.answer(
            "AI spend today:\n"
            f"  spent: ${summary['spend_usd']:.4f}\n"
            f"  budget: ${summary['budget_usd']:.2f}\n"
            f"  remaining: ${summary['remaining_usd']:.4f}",
        )

    @router.message(Command("agents"))
    @admin_only("/agents")
    async def cmd_agents_perf(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        snaps = adaptive.control_plane.learning.latest_agent_snapshots()
        if not snaps:
            snaps = adaptive.control_plane.analytics.snapshot_agents_from_outcomes()
        lines = ["Agent performance:", ""]
        for snap in snaps:
            lines.append(
                f"- {snap.agent_name}: acc={snap.accuracy:.2f} "
                f"fp={snap.false_positive_rate:.2f} pub={snap.publish_success:.2f}"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("replay"))
    @admin_only("/replay")
    async def cmd_replay(message: Message) -> None:
        if adaptive is None or adaptive.control_plane.replay is None:
            await message.answer("Replay engine unavailable.")
            return
        parts = (message.text or "").split()
        if len(parts) < 3:
            runs = adaptive.control_plane.learning.list_replay_runs(limit=5)
            if not runs:
                await message.answer(
                    "Usage: /replay <from_iso> <to_iso>\nNo replay runs yet.",
                )
                return
            lines = ["Recent replays:", ""]
            for run in runs:
                lines.append(
                    f"- #{run['id']} {run['run_label']} events={run['events_processed']} "
                    f"matched={run['signals_matched']}"
                )
            await message.answer("\n".join(lines)[:3900])
            return
        result = adaptive.control_plane.replay.run(
            from_ts=parts[1],
            to_ts=parts[2],
            run_label="admin",
        )
        await message.answer(
            f"Replay #{result.run_id}: events={result.events_processed} "
            f"matched={result.signals_matched} policy={result.policy_name}",
        )

    @router.message(Command("memory"))
    @admin_only("/memory")
    async def cmd_memory(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""
        if query:
            records = adaptive.control_plane.memory.recall(query, limit=8)
        else:
            records = adaptive.control_plane.memory.top_precedents(limit=8)
        if not records:
            await message.answer("No long-term memory entries.")
            return
        lines = ["Editorial memory:", ""]
        for row in records:
            lines.append(
                f"- [{row.memory_type}] {row.title[:80]} "
                f"(rel={row.relevance_score:.2f} n={row.occurrence_count})"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("sources"))
    @admin_only("/sources")
    async def cmd_adaptive_sources(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        weights = adaptive.control_plane.learning.list_source_weights(limit=12)
        if not weights:
            updated = 0
            if adaptive.control_plane.source_weights is not None:
                updated = adaptive.control_plane.source_weights.recompute_all()
            await message.answer(
                f"No dynamic weights yet. Recomputed {updated} sources.",
            )
            return
        lines = ["Dynamic source weights:", ""]
        for row in weights:
            lines.append(
                f"- {row['source_name']}: weight={float(row['dynamic_weight']):.3f} "
                f"false_esc={float(row['false_escalation_rate']):.2f} "
                f"({row.get('adjustment_reason') or '-'})"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("learn"))
    @admin_only("/learn")
    async def cmd_learn_cycle(message: Message) -> None:
        if adaptive is None:
            await message.answer("Adaptive control plane unavailable.")
            return
        result = adaptive.control_plane.run_learning_cycle()
        scores = result["scores"]
        await message.answer(
            "Learning cycle complete.\n"
            f"feedback_signals={result['feedback_signals']}\n"
            f"sources_updated={result['sources_updated']}\n"
            f"signal_precision={scores.signal_precision_score:.2f}\n"
            f"forecast_reliability={scores.forecast_reliability_score:.2f}\n"
            f"snr={scores.signal_to_noise_ratio:.2f}",
        )

    dp.include_router(router)


def _esc_impact(text: str) -> str:
    import html

    return html.escape((text or "")[:90])
