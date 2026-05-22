from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram.enums import ParseMode

from publisher.publish_formatting import build_channel_message_html
from publisher.rate_limit import get_publish_rate_limiter
from publisher.retry import async_retry
from publisher.routing import route_draft_to_channel
from utils.metrics import inc
from utils.structured_log import log_event
from utils.telegram_chunks import split_telegram_text

if TYPE_CHECKING:
    from aiogram import Bot

    from app.config import Settings

logger = logging.getLogger(__name__)


def _routing_kwargs_from_extras(extras_json: str | None) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if not extras_json:
        return d
    try:
        ex = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return d
    if not isinstance(ex, dict):
        return d
    tags = ex.get("tags")
    if isinstance(tags, list):
        d["tags"] = [str(t) for t in tags]
    inf = ex.get("inferred_tags")
    if isinstance(inf, list):
        merged = list(d.get("tags") or [])
        merged.extend(str(t) for t in inf if t)
        d["tags"] = sorted(set(merged))[:24]
    dup = ex.get("duplicate_intel") if isinstance(ex.get("duplicate_intel"), dict) else {}
    sev_top = ex.get("severity")
    if isinstance(sev_top, str) and sev_top.strip():
        d["severity"] = sev_top.strip()
    elif dup.get("severity"):
        d["severity"] = str(dup.get("severity"))
    cat = ex.get("category")
    if isinstance(cat, str):
        d["category"] = cat
    return d


async def publish_draft_to_channel(
    bot: "Bot",
    settings: "Settings",
    *,
    draft_id: int,
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    draft_extras_json: str | None = None,
    manual_channel_id: int | None = None,
) -> int:
    """
    Send draft to resolved channel (HTML chunks, routing-aware). Returns first channel message id.
    """
    src_list: list[dict[str, Any]] | None
    if isinstance(sources, list):
        src_list = sources
    else:
        src_list = None
    rk = _routing_kwargs_from_extras(draft_extras_json)
    chat_id = route_draft_to_channel(
        settings,
        tags=rk.get("tags"),
        category=rk.get("category"),
        severity=rk.get("severity"),
        sources=src_list,
        manual_channel_id=manual_channel_id,
    )
    limiter = get_publish_rate_limiter(
        min_interval_sec=settings.publish_channel_min_interval_sec,
        burst_window_sec=settings.publish_burst_window_sec,
        burst_max_messages=settings.publish_burst_max_messages,
    )
    await limiter.acquire_before_publish(int(chat_id))
    html = build_channel_message_html(content, sources or "[]", draft_id=draft_id)
    chunks = split_telegram_text(html, respect_html=True)
    sent_ids: list[int] = []
    for idx, chunk in enumerate(chunks):

        async def _send() -> int:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return int(msg.message_id)

        try:
            mid = await async_retry(_send, attempts=3, delay_sec=0.6, label=f"publish_chunk_{draft_id}_{idx}")
        except BaseException as exc:
            inc("telegram_api_failures")
            log_event(
                logger,
                "publish.telegram_api_error",
                draft_id=draft_id,
                chunk_index=idx,
                channel_id=chat_id,
                error=repr(exc)[:500],
            )
            raise exc
        log_event(
            logger,
            "publish.telegram_message_sent",
            draft_id=draft_id,
            chunk_index=idx,
            channel_id=chat_id,
            message_id=mid,
        )
        sent_ids.append(mid)
        if idx < len(chunks) - 1 and settings.telegram_inter_chunk_delay_sec > 0:
            await asyncio.sleep(settings.telegram_inter_chunk_delay_sec)

    log_event(
        logger,
        "publisher.chunks_sent",
        draft_id=draft_id,
        chunk_count=len(sent_ids),
        channel_id=chat_id,
        duration_sec=round(time.perf_counter(), 4),
    )
    return sent_ids[0]


# Spec / tests: stable name for the same entrypoint.
publish_draft = publish_draft_to_channel
