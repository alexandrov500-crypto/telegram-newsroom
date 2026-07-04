"""Breaking fast lane: publish first, persist metadata after (no pre-publish DB)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from aiogram.enums import ParseMode

from app.config import Settings
from publisher.rate_limit import get_publish_rate_limiter
from publisher.retry import async_retry
from publisher.routing import route_draft_to_channel
from utils.metrics import inc
from utils.structured_log import log_event
from utils.telegram_chunks import split_telegram_text

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")


def quick_sanitize(text: str, *, max_chars: int = 2400) -> str:
    t = _WS.sub(" ", (text or "").strip())
    if len(t) > max_chars:
        t = t[: max_chars - 3].rstrip() + "..."
    return t


def build_breaking_html(content: str, sources: list[dict[str, Any]], *, article_id: str) -> str:
    """Fast-lane HTML via the same public renderer as the main lane (SSOT, no debug tail)."""
    _ = article_id  # correlation id stays in logs only — never in the public post
    from app.editorial.public_post_formatter import format_public_post_html

    return format_public_post_html(
        content,
        sources,
        growth_meta={"is_breaking": True},
    )


async def publish_breaking_item(
    bot: Any,
    settings: Settings,
    *,
    content: str,
    sources: list[dict[str, Any]],
    article_id: str,
) -> int:
    """Send breaking post to target channel. Returns Telegram message id."""
    from app.operational_mode import load_operational_mode, publish_allowed

    op = load_operational_mode(settings.runtime_state_dir, settings)
    if not publish_allowed(op, settings):
        raise RuntimeError(f"publish_blocked:operational_mode={op.value}")

    if settings.dry_run:
        log_event(logger, "breaking.publish_skipped", reason="dry_run", article_id=article_id)
        return 0

    chat_id = route_draft_to_channel(
        settings,
        tags=["breaking"],
        severity="high",
        sources=sources,
    )
    limiter = get_publish_rate_limiter(
        min_interval_sec=max(0.05, settings.publish_channel_min_interval_sec * 0.25),
        burst_window_sec=settings.publish_burst_window_sec,
        burst_max_messages=settings.publish_burst_max_messages,
    )
    await limiter.acquire_before_publish(int(chat_id))

    html = build_breaking_html(content, sources, article_id=article_id)
    from app.editorial.publish_pipeline_guards import enforce_publish_html_guards

    enforce_publish_html_guards(html, draft_id=None, settings=settings)
    chunks = split_telegram_text(html, respect_html=True)
    sent_id = 0
    for idx, chunk in enumerate(chunks):

        async def _send(c: str = chunk) -> int:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=c,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return int(msg.message_id)

        sent_id = await async_retry(_send, attempts=3, delay_sec=0.35, label=f"breaking_{article_id}_{idx}")
        if idx < len(chunks) - 1 and settings.telegram_inter_chunk_delay_sec > 0:
            await asyncio.sleep(min(0.2, settings.telegram_inter_chunk_delay_sec))

    inc("breaking_lane_published_total")
    inc("publishes")
    log_event(
        logger,
        "breaking.publish_ok",
        article_id=article_id,
        channel_id=chat_id,
        message_id=sent_id,
    )
    return sent_id


def schedule_post_publish_write(
    *,
    settings: Settings,
    item: dict[str, Any],
    message_id: int,
    latency_sec: float,
) -> None:
    """Async post-write: journal + ops event (never blocks publish path)."""

    async def _write() -> None:
        try:
            from ops.pipeline.observability import emit_ops_event
            from ops.resilience.publish_journal import append_journal, new_publish_tx_id

            article_id = str(item.get("news_id") or item.get("ingest_key") or "")[:32]
            emit_ops_event(
                "breaking_published",
                runtime_dir=settings.runtime_state_dir,
                news_id=article_id,
                state="published",
                decision_reason="fast_lane",
                message_id=message_id,
                latency_sec=round(latency_sec, 3),
            )
            from app.ops.ledger.writer import record_published

            record_published(
                item,
                channel_message_id=message_id,
                lane="breaking",
                latency_sec=round(latency_sec, 3),
            )
            append_journal(
                settings.runtime_state_dir,
                tx_id=new_publish_tx_id(),
                draft_id=0,
                state="finalized",
                idempotency_key=f"breaking:{article_id}",
                channel_message_id=message_id,
                extra={"lane": "breaking", "source": item.get("source")},
            )
        except Exception as exc:
            logger.warning("breaking post-write failed: %s", exc)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write(), name="breaking_post_write")
    except RuntimeError:
        pass
