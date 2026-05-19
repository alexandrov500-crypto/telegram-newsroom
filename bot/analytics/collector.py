from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.storage.analytics_repository import AnalyticsRepository, PublishedPost

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PostMetrics:
    views: int = 0
    forwards: int = 0
    reactions: int = 0


async def _fetch_via_telethon(
    *,
    channel_id: int,
    message_id: int,
    telethon_settings: Any,
) -> PostMetrics | None:
    try:
        from bot.ingestion.telethon_client import create_telegram_client, ensure_connected

        client = create_telegram_client(telethon_settings)
        connected = await ensure_connected(client)
        if not connected:
            return None
        message = await client.get_messages(channel_id, ids=message_id)
        if message is None:
            return None
        views = int(getattr(message, "views", None) or 0)
        forwards = int(getattr(message, "forwards", None) or 0)
        reactions = 0
        reactions_obj = getattr(message, "reactions", None)
        if reactions_obj is not None:
            results = getattr(reactions_obj, "results", None) or []
            reactions = sum(int(getattr(result, "count", 0) or 0) for result in results)
        return PostMetrics(views=views, forwards=forwards, reactions=reactions)
    except Exception:
        logger.exception(
            "event=analytics_collected action=telethon_fetch_failed message_id=%d",
            message_id,
        )
        return None


async def fetch_post_metrics(
    bot: Bot,
    *,
    channel_id: int,
    message_id: int,
    telethon_settings: Any | None = None,
    previous_views: int = 0,
) -> PostMetrics:
    """Collect metrics for a channel post. Fail-open with previous/zero values."""
    _ = bot
    if telethon_settings is not None:
        telethon_metrics = await _fetch_via_telethon(
            channel_id=channel_id,
            message_id=message_id,
            telethon_settings=telethon_settings,
        )
        if telethon_metrics is not None:
            return telethon_metrics

    try:
        # Bot API has limited per-message stats; preserve last known views when unavailable.
        return PostMetrics(views=previous_views, forwards=0, reactions=0)
    except TelegramAPIError:
        logger.warning(
            "event=analytics_collected action=bot_fetch_failed message_id=%d",
            message_id,
        )
        return PostMetrics(views=previous_views, forwards=0, reactions=0)
    except Exception:
        logger.exception(
            "event=analytics_collected action=fetch_failed message_id=%d",
            message_id,
        )
        return PostMetrics(views=previous_views, forwards=0, reactions=0)


async def collect_post_analytics(
    repo: AnalyticsRepository,
    bot: Bot,
    *,
    channel_id: int | None,
    telethon_settings: Any | None = None,
    limit: int = 40,
) -> int:
    """Poll recent published posts and persist analytics. Never raises."""
    if channel_id is None:
        return 0
    collected = 0
    posts = repo.list_posts_for_collection(limit=limit)
    for post in posts:
        if post.telegram_message_id is None:
            continue
        try:
            metrics = await fetch_post_metrics(
                bot,
                channel_id=channel_id,
                message_id=int(post.telegram_message_id),
                telethon_settings=telethon_settings,
                previous_views=post.latest_views,
            )
            topics = _parse_json_list(post.topics_json)
            virality = repo.topic_virality(topics)
            score = repo.record_analytics_snapshot(
                post.id,
                views=metrics.views,
                forwards=metrics.forwards,
                reactions=metrics.reactions,
                source_trust=post.source_trust,
                topic_virality=virality,
            )
            if score is not None:
                repo.learn_from_post(post, score)
                collected += 1
        except Exception:
            logger.exception(
                "event=analytics_collected action=post_failed post_id=%d",
                post.id,
            )
    if collected:
        logger.info("event=analytics_collected count=%d", collected)
    return collected


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        import json

        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        return []
    return []
