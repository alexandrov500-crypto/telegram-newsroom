from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from telethon.errors import FloodWaitError, RPCError
from telethon.utils import get_peer_id

from bot.config import project_root
from bot.ingestion.normalize import message_to_normalized, normalize_channel_ref, title_from_text
from bot.processing.media import extract_telegram_media, resolve_telegram_media_url
from bot.ingestion.pipeline import IngestOutcome, ingest_news_item
from bot.ingestion.rss import NewsItem
from bot.ingestion.telethon_client import (
    TelethonSettings,
    create_telegram_client,
    ensure_connected,
    handle_flood_wait,
)
from bot.runtime.state import runtime_state
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.repository import LinkDedup
from bot.editorial.agent_service import EditorialAgentService
from bot.editorial.story_memory import StoryMemoryService
from bot.signals.signal_service import SignalIntelligenceService
from bot.adaptive.service import AdaptiveOperationsService
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.entity_repository import EntityRepository
from bot.observability.registry import ObservabilityRegistry
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.source_repository import SourceRepository
from bot.storage.telegram_seen_repository import TelegramSeenRepository

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 60
_MESSAGES_PER_CHANNEL = 25


async def _fetch_recent_messages(client, channel: str, *, limit: int) -> list:
    messages: list = []
    async for message in client.iter_messages(channel, limit=limit):
        if getattr(message, "message", None):
            messages.append(message)
    return messages


async def _process_channel(
    client,
    channel_ref: str,
    *,
    telegram_seen: TelegramSeenRepository,
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
    registry: ObservabilityRegistry | None = None,
) -> tuple[int, int]:
    ingested = 0
    skipped = 0
    channel_key = channel_ref

    try:
        entity = await client.get_entity(channel_ref)
        channel_display = (
            getattr(entity, "username", None)
            or getattr(entity, "title", None)
            or channel_ref
        )
        try:
            channel_key = str(get_peer_id(entity))
        except Exception:
            if getattr(entity, "username", None):
                channel_key = f"@{entity.username}"
    except Exception:
        channel_display = channel_ref
        logger.warning(
            "event=telegram_channel_resolve_failed channel=%r",
            channel_ref,
        )

    try:
        messages = await _fetch_recent_messages(
            client,
            channel_ref,
            limit=_MESSAGES_PER_CHANNEL,
        )
    except FloodWaitError as exc:
        await handle_flood_wait(exc)
        return ingested, skipped
    except RPCError:
        logger.exception(
            "event=telegram_ingestion_failed channel=%r reason=fetch_failed",
            channel_ref,
        )
        return ingested, skipped
    except Exception:
        logger.exception(
            "event=telegram_ingestion_failed channel=%r reason=unexpected_fetch",
            channel_ref,
        )
        return ingested, skipped

    for message in reversed(messages):
        message_id = int(message.id)
        if telegram_seen.is_seen(channel_key, message_id):
            skipped += 1
            logger.info(
                "event=telegram_duplicate_skipped channel=%r message_id=%d",
                channel_key,
                message_id,
            )
            continue

        published = None
        if getattr(message, "date", None):
            published = message.date
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)

        raw_text = getattr(message, "message", None)
        normalized = message_to_normalized(
            text=raw_text,
            channel_display=str(channel_display),
            channel_key=channel_key,
            message_id=message_id,
            published=published,
        )
        telegram_media = extract_telegram_media(message)
        if normalized is None:
            if not telegram_media.has_media:
                continue
            caption_text = (raw_text or "").strip() or "Media update"
            normalized = message_to_normalized(
                text=caption_text if len(caption_text) >= 20 else caption_text + " " + ("." * 20),
                channel_display=str(channel_display),
                channel_key=channel_key,
                message_id=message_id,
                published=published,
            )
            if normalized is None:
                from bot.ingestion.normalize import NormalizedTelegramMessage, build_telegram_link

                normalized = NormalizedTelegramMessage(
                    title=title_from_text(caption_text) or f"{channel_display} update",
                    text=caption_text,
                    source=str(channel_display),
                    channel_key=channel_key,
                    message_id=message_id,
                    link=build_telegram_link(channel_key, message_id),
                    published=published,
                )
        if telegram_media.has_media and not telegram_media.media_url:
            try:
                cache_dir = project_root() / "data" / "media_cache"
                telegram_media = await resolve_telegram_media_url(
                    client,
                    message,
                    telegram_media,
                    cache_dir=cache_dir,
                )
            except Exception:
                logger.exception("event=media_extract_failed source=telegram_cache")

        item = NewsItem(
            title=normalized.title,
            link=normalized.link,
            published=normalized.published,
            source=f"telegram:{normalized.source}",
            media_type=telegram_media.media_type,
            media_url=telegram_media.media_url,
            thumbnail_url=telegram_media.thumbnail_url,
            media_width=telegram_media.width,
            media_height=telegram_media.height,
        )
        result = await ingest_news_item(
            item,
            dedup=dedup,
            editorial=editorial,
            clusters=clusters,
            sources=sources,
            entities=entities,
            analytics=analytics,
            agents=agents,
            localizations=localizations,
            story_memory=story_memory,
            signal_intel=signal_intel,
            adaptive=adaptive,
        )
        telegram_seen.mark_seen(channel_key, message_id)

        if result.outcome == IngestOutcome.ENQUEUED:
            ingested += 1
            runtime_state.telegram_messages_ingested += 1
            logger.info(
                "event=telegram_message_ingested channel=%r message_id=%d link=%r",
                channel_key,
                message_id,
                item.link,
            )
        elif result.outcome == IngestOutcome.CLUSTER_MATCHED:
            ingested += 1
            runtime_state.telegram_messages_ingested += 1
            logger.info(
                "event=telegram_message_ingested channel=%r message_id=%d "
                "outcome=cluster_matched",
                channel_key,
                message_id,
            )

    return ingested, skipped


async def run_telegram_ingestion_loop(
    settings: TelethonSettings,
    source_channels: Sequence[str],
    telegram_seen: TelegramSeenRepository,
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
    registry: ObservabilityRegistry | None = None,
    *,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
) -> None:
    """Poll Telegram source channels. Isolated from RSS; never raises."""
    if not source_channels:
        logger.warning(
            "event=telegram_ingestion_disabled reason='TELEGRAM_SOURCE_CHANNELS empty'"
        )
        while True:
            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise

    client = create_telegram_client(settings)
    logger.info("event=telegram_ingestion_started channel_count=%d", len(source_channels))

    while True:
        try:
            if runtime_state.ingestion_paused:
                await asyncio.sleep(interval_sec)
                continue

            runtime_state.telegram_last_cycle_at = datetime.now(timezone.utc)
            connected = await ensure_connected(client)
            runtime_state.telegram_connected = connected
            if not connected:
                runtime_state.telegram_last_error = "not_connected"
                await asyncio.sleep(interval_sec)
                continue

            runtime_state.telegram_last_error = None
            total_ingested = 0
            total_skipped = 0

            for channel_ref in source_channels:
                ingested, skipped = await _process_channel(
                    client,
                    channel_ref,
                    telegram_seen=telegram_seen,
                    dedup=dedup,
                    editorial=editorial,
                    clusters=clusters,
                    sources=sources,
                    entities=entities,
                    analytics=analytics,
                    agents=agents,
                    localizations=localizations,
                    story_memory=story_memory,
                    signal_intel=signal_intel,
                    adaptive=adaptive,
                    registry=registry,
                )
                total_ingested += ingested
                total_skipped += skipped

            if registry is not None:
                await registry.mark_telegram_cycle(
                    connected=runtime_state.telegram_connected,
                )
            logger.info(
                "event=telegram_ingestion_cycle_complete ingested=%d skipped=%d",
                total_ingested,
                total_skipped,
            )
        except asyncio.CancelledError:
            logger.info("event=telegram_ingestion_stopped")
            if client.is_connected():
                await client.disconnect()
            raise
        except FloodWaitError as exc:
            runtime_state.telegram_last_error = f"flood_wait:{exc.seconds}"
            await handle_flood_wait(exc)
        except Exception as exc:
            runtime_state.telegram_last_error = repr(exc)
            logger.exception("event=telegram_ingestion_failed")

        await asyncio.sleep(interval_sec)
