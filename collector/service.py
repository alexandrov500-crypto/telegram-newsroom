from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import RPCError

from collector.channel_profile import ChannelCollectStats
from collector.retry import ensure_connected, with_telethon_retries
from collector.telethon_client import to_utc_aware
from collector.telethon_media import (
    detect_media_type,
    download_message_media,
    message_plain_text,
)
from db.models import RawPost
from db.repository import upsert_raw_post
from utils.structured_log import log_event

if TYPE_CHECKING:
    from collector.progress import CollectProgress

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
    stats = ChannelCollectStats(channel=label)
    stats.emit_start()

    def _media_skip_channels() -> set[str]:
        raw = os.getenv("COLLECTOR_MEDIA_SKIP_CHANNELS", "")
        return {c.strip().lower().lstrip("@") for c in raw.split(",") if c.strip()}

    async def iterate_messages():
        await ensure_connected(client)
        count = 0
        media_cache = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")) / "media_cache"
        collect_media = os.getenv("COLLECTOR_MEDIA_ENABLED", "true").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        channel_key = label.lower().lstrip("@")
        skip_media = channel_key in _media_skip_channels()
        async for message in client.iter_messages(entity, limit=limit):
            stats.record_scan()
            text = message_plain_text(message)
            has_media = detect_media_type(message) != "none"
            if not text and not has_media:
                continue
            stats.record_fetched()
            extras: dict[str, object] = {}
            msg_id = int(message.id)
            already_stored = await session.scalar(
                select(RawPost.id).where(
                    RawPost.channel_name == label,
                    RawPost.message_id == msg_id,
                )
            )
            if collect_media and has_media and not skip_media and already_stored is None:
                stats.media_downloads += 1
                media_payload = await download_message_media(client, message, media_cache)
                if media_payload:
                    extras["media"] = media_payload
            elif collect_media and has_media and not skip_media and already_stored is not None:
                stats.media_skipped_existing += 1
            from app.editorial.source_languages import language_for_channel

            src_lang = language_for_channel(label)
            if src_lang:
                extras["source_language"] = src_lang
            created = to_utc_aware(message.date)
            was_new = await upsert_raw_post(
                session,
                channel_name=label,
                message_id=msg_id,
                text=text or " ",
                created_at=created,
                extras_json=json.dumps(extras, ensure_ascii=False),
            )
            if was_new:
                stats.record_new()
                count += 1
                try:
                    from ops.pipeline.ingest_hooks import on_raw_post_inserted

                    meta = on_raw_post_inserted(
                        runtime_dir=os.getenv("RUNTIME_STATE_DIR", "var/runtime"),
                        channel_name=label,
                        message_id=msg_id,
                        text=text or " ",
                    )
                    if meta.get("duplicate"):
                        count = max(0, count - 1)
                        stats.new_rows_written = max(0, stats.new_rows_written - 1)
                except Exception as exc:
                    stats.record_exception()
                    log_event(
                        logger,
                        "collector.ops_hook_failed",
                        channel=label,
                        error=repr(exc)[:200],
                    )
            else:
                stats.record_dedup()
        return count

    try:
        inserted = await with_telethon_retries(
            f"iter_messages:{label}",
            iterate_messages,
            max_attempts=telethon_max_attempts,
        )
    except RPCError as exc:
        stats.record_exception()
        stats.emit_runtime()
        stats.emit_summary()
        log_event(logger, "collector.iter_failed", channel=label, error=str(exc))
        return 0
    except Exception as exc:
        stats.record_exception()
        stats.emit_runtime()
        stats.emit_summary()
        log_event(logger, "collector.iter_failed", channel=label, error=repr(exc))
        return 0

    stats.emit_runtime()
    stats.emit_summary()
    log_event(logger, "collector.channel_done", channel=label, new_rows=inserted, runtime_sec=round(stats.runtime_sec, 3))
    return inserted


async def _commit_after_channel(
    session: AsyncSession,
    *,
    channel: str,
    new_rows: int,
    progress: CollectProgress | None,
) -> None:
    t0 = time.perf_counter()
    await session.commit()
    commit_sec = time.perf_counter() - t0
    if progress is not None:
        progress.record_channel(channel, new_rows, commit_sec=commit_sec)


async def collect_all_channels(
    client: TelegramClient,
    session: AsyncSession,
    *,
    channels: Iterable[str],
    limit_per_channel: int,
    telethon_max_attempts: int,
    channel_delay_seconds: float,
    progress: CollectProgress | None = None,
) -> int:
    total = 0
    channel_list = list(channels)
    for idx, channel in enumerate(channel_list):
        new_rows = await collect_channel_messages(
            client,
            session,
            channel=channel,
            limit=limit_per_channel,
            telethon_max_attempts=telethon_max_attempts,
        )
        total += new_rows
        await _commit_after_channel(session, channel=channel, new_rows=new_rows, progress=progress)
        if idx < len(channel_list) - 1 and channel_delay_seconds > 0:
            await asyncio.sleep(channel_delay_seconds)
    log_event(logger, "collector.batch_done", channel_count=len(channel_list), new_rows_total=total)
    return total


async def shutdown_collector_hooks() -> None:
    """Lifecycle hook: reserved for shared collector resources (no-op in MVP)."""
    log_event(logger, "collector.shutdown_hooks_complete")
