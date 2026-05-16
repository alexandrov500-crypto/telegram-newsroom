from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import RPCError

from collector.retry import ensure_connected, with_telethon_retries
from collector.telethon_client import to_utc_aware
from db.repository import upsert_raw_post
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _channel_label(entity: object) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    return str(getattr(entity, "id", "unknown"))


async def collect_channel_messages(
    client: TelegramClient,
    session: AsyncSession,
    *,
    channel: str,
    limit: int,
    telethon_max_attempts: int,
) -> int:
    inserted = 0

    async def resolve_entity():
        await ensure_connected(client)
        return await client.get_entity(channel)

    try:
        entity = await with_telethon_retries(
            f"get_entity:{channel}",
            resolve_entity,
            max_attempts=telethon_max_attempts,
        )
    except ValueError as exc:
        log_event(logger, "collector.resolve_failed", channel=channel, error=str(exc))
        return 0
    except Exception as exc:
        log_event(logger, "collector.resolve_failed", channel=channel, error=repr(exc))
        return 0

    label = _channel_label(entity)

    async def iterate_messages():
        await ensure_connected(client)
        count = 0
        async for message in client.iter_messages(entity, limit=limit):
            if not message.text:
                continue
            created = to_utc_aware(message.date)
            was_new = await upsert_raw_post(
                session,
                channel_name=label,
                message_id=int(message.id),
                text=message.text,
                created_at=created,
            )
            if was_new:
                count += 1
        return count

    try:
        inserted = await with_telethon_retries(
            f"iter_messages:{label}",
            iterate_messages,
            max_attempts=telethon_max_attempts,
        )
    except RPCError as exc:
        log_event(logger, "collector.iter_failed", channel=label, error=str(exc))
        return 0
    except Exception as exc:
        log_event(logger, "collector.iter_failed", channel=label, error=repr(exc))
        return 0

    log_event(logger, "collector.channel_done", channel=label, new_rows=inserted)
    return inserted


async def collect_all_channels(
    client: TelegramClient,
    session: AsyncSession,
    *,
    channels: Iterable[str],
    limit_per_channel: int,
    telethon_max_attempts: int,
    channel_delay_seconds: float,
) -> int:
    total = 0
    channel_list = list(channels)
    for idx, channel in enumerate(channel_list):
        total += await collect_channel_messages(
            client,
            session,
            channel=channel,
            limit=limit_per_channel,
            telethon_max_attempts=telethon_max_attempts,
        )
        if idx < len(channel_list) - 1 and channel_delay_seconds > 0:
            await asyncio.sleep(channel_delay_seconds)
    log_event(logger, "collector.batch_done", channel_count=len(channel_list), new_rows_total=total)
    return total


async def shutdown_collector_hooks() -> None:
    """Lifecycle hook: reserved for shared collector resources (no-op in MVP)."""
    log_event(logger, "collector.shutdown_hooks_complete")
