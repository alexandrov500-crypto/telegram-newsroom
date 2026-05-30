"""Parallel sharded Telethon collection with backpressure."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient

from collector.service import _commit_after_channel, collect_all_channels, collect_channel_messages
from utils.structured_log import log_event

if TYPE_CHECKING:
    from collector.progress import CollectProgress

logger = logging.getLogger(__name__)


def _parallel_enabled() -> bool:
    return os.getenv("COLLECT_PARALLEL_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _shard_size() -> int:
    try:
        return max(1, min(8, int(os.getenv("COLLECT_SHARD_SIZE", "3"))))
    except ValueError:
        return 3


def _max_inflight() -> int:
    try:
        return max(1, min(4, int(os.getenv("COLLECT_MAX_INFLIGHT_SHARDS", "2"))))
    except ValueError:
        return 2


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def collect_channels_sharded(
    client: TelegramClient,
    session: AsyncSession,
    *,
    channels: Iterable[str],
    limit_per_channel: int,
    telethon_max_attempts: int,
    channel_delay_seconds: float,
    progress: CollectProgress | None = None,
) -> int:
    """
    Gather collection by shard groups; semaphore limits concurrent shards (backpressure).
    """
    channel_list = list(channels)
    if not channel_list:
        return 0
    if not _parallel_enabled() or len(channel_list) <= 1:
        return await collect_all_channels(
            client,
            session,
            channels=channel_list,
            limit_per_channel=limit_per_channel,
            telethon_max_attempts=telethon_max_attempts,
            channel_delay_seconds=channel_delay_seconds,
            progress=progress,
        )

    shards = _chunked(channel_list, _shard_size())
    sem = asyncio.Semaphore(_max_inflight())
    total = 0

    async def _run_shard(shard: list[str]) -> int:
        async with sem:
            sub = 0
            for idx, ch in enumerate(shard):
                new_rows = await collect_channel_messages(
                    client,
                    session,
                    channel=ch,
                    limit=limit_per_channel,
                    telethon_max_attempts=telethon_max_attempts,
                )
                sub += new_rows
                await _commit_after_channel(session, channel=ch, new_rows=new_rows, progress=progress)
                if idx < len(shard) - 1 and channel_delay_seconds > 0:
                    await asyncio.sleep(channel_delay_seconds * 0.5)
            return sub

    results = await asyncio.gather(*[_run_shard(s) for s in shards], return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            log_event(logger, "collector.shard_failed", error=repr(r)[:200])
            continue
        total += int(r)
    log_event(
        logger,
        "collector.sharded_batch_done",
        channel_count=len(channel_list),
        shard_count=len(shards),
        new_rows_total=total,
    )
    return total
