from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from publisher.draft_media import media_from_extras_json
from publisher.publish_formatting import build_channel_message_html
from publisher.rate_limit import get_publish_rate_limiter
from publisher.retry import async_retry
from publisher.routing import route_draft_to_channel
from publisher.telegram_transport import (
    send_channel_message,
    send_channel_photo,
    send_channel_video,
)
from utils.metrics import inc
from utils.structured_log import log_event
from utils.telegram_chunks import split_telegram_text

if TYPE_CHECKING:
    from aiogram import Bot

    from app.config import Settings

logger = logging.getLogger(__name__)

_TELEGRAM_CAPTION_LIMIT = 1024


def _publish_fallback_media_enabled() -> bool:
    explicit = os.getenv("PUBLISH_FALLBACK_MEDIA", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    return os.getenv("MEDIA_BRANDED_FALLBACK_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _video_strict_adapt_enabled() -> bool:
    return (
        __import__("os")
        .getenv("TELEGRAM_VIDEO_STRICT_ADAPT", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )


def _is_video_telegram_compatible(media: dict[str, Any]) -> bool:
    if str(media.get("media_type") or "") != "video":
        return True
    try:
        w = int(media.get("width") or 0)
        h = int(media.get("height") or 0)
    except (TypeError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    ratio = w / max(h, 1)
    return 1.70 <= ratio <= 1.82


async def _maybe_adapt_video_for_publish(
    *,
    media: dict[str, Any],
    draft_id: int,
) -> dict[str, Any] | None:
    if str(media.get("media_type") or "") != "video":
        return media
    if _is_video_telegram_compatible(media):
        return media
    src = Path(str(media.get("local_path") or ""))
    if not src.is_file():
        return None
    try:
        from publisher.video_normalize import normalize_video_for_telegram

        normalized = await normalize_video_for_telegram(
            src,
            src.parent,
            draft_id=draft_id,
        )
    except Exception:
        normalized = None
    if not normalized:
        return None
    out = dict(media)
    out.update(normalized)
    out["media_type"] = "video"
    out["local_path"] = str(normalized.get("local_path") or src)
    return out


def publish_transport_key(draft_id: int, publish_attempt: int = 1) -> str:
    """Stable transport correlation id (idempotency keys are owned by publish_service)."""
    return f"draft:{int(draft_id)}:attempt:{int(publish_attempt)}"


def _record_send_success(draft_id: int) -> None:
    try:
        from app.observability.telegram_production import record_telegram_success

        record_telegram_success(draft_id=draft_id)
    except Exception:
        pass


def _record_send_failure(draft_id: int, error: str) -> None:
    try:
        from app.observability.telegram_production import record_telegram_api_failure

        record_telegram_api_failure(draft_id=draft_id, error=error)
    except Exception:
        pass


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


async def _send_text_chunks(
    bot: "Bot",
    *,
    chat_id: int,
    chunks: list[str],
    draft_id: int,
    settings: "Settings",
    publish_attempt: int = 1,
) -> list[int]:
    sent_ids: list[int] = []
    for idx, chunk in enumerate(chunks):

        async def _send(c: str = chunk) -> int:
            return await send_channel_message(
                bot,
                text=c,
                chat_id=chat_id,
                draft_id=draft_id,
                publish_attempt=publish_attempt,
                disable_web_page_preview=True,
            )

        try:
            mid = await async_retry(_send, attempts=3, delay_sec=0.6, label=f"publish_chunk_{draft_id}_{idx}")
        except BaseException as exc:
            inc("telegram_api_failures")
            _record_send_failure(draft_id, repr(exc))
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
        if idx == 0:
            _record_send_success(draft_id)
        sent_ids.append(mid)
        if idx < len(chunks) - 1 and settings.telegram_inter_chunk_delay_sec > 0:
            await asyncio.sleep(settings.telegram_inter_chunk_delay_sec)
    return sent_ids


async def _send_with_media(
    bot: "Bot",
    *,
    chat_id: int,
    media: dict[str, Any],
    chunks: list[str],
    draft_id: int,
    settings: "Settings",
    publish_attempt: int = 1,
) -> int:
    from aiogram.types import FSInputFile

    media_type = str(media["media_type"])
    local_path = str(media["local_path"])
    upload = FSInputFile(local_path)

    async def _send_media(caption: str | None) -> int:
        if media_type == "photo":
            return await send_channel_photo(
                bot,
                photo=upload,
                chat_id=chat_id,
                caption=caption,
                draft_id=draft_id,
                publish_attempt=publish_attempt,
            )
        return await send_channel_video(
            bot,
            video=upload,
            chat_id=chat_id,
            caption=caption,
            draft_id=draft_id,
            publish_attempt=publish_attempt,
            width=int(media["width"]) if media.get("width") else None,
            height=int(media["height"]) if media.get("height") else None,
            duration=int(media["duration"]) if media.get("duration") else None,
        )

    first_chunk = chunks[0] if chunks else ""
    rest = chunks[1:]
    if first_chunk and len(first_chunk) <= _TELEGRAM_CAPTION_LIMIT:
        first_id = await async_retry(
            lambda: _send_media(first_chunk),
            attempts=3,
            delay_sec=0.6,
            label=f"publish_media_{draft_id}",
        )
        if rest:
            await _send_text_chunks(
                bot,
                chat_id=chat_id,
                chunks=rest,
                draft_id=draft_id,
                settings=settings,
                publish_attempt=publish_attempt,
            )
        return first_id

    first_id = await async_retry(
        lambda: _send_media(None),
        attempts=3,
        delay_sec=0.6,
        label=f"publish_media_{draft_id}",
    )
    if chunks:
        await _send_text_chunks(
            bot,
            chat_id=chat_id,
            chunks=chunks,
            draft_id=draft_id,
            settings=settings,
            publish_attempt=publish_attempt,
        )
    return first_id


async def publish_draft_to_channel(
    bot: "Bot",
    settings: "Settings",
    *,
    draft_id: int,
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    draft_extras_json: str | None = None,
    manual_channel_id: int | None = None,
    publish_attempt: int = 1,
    bypass_rate_limit: bool = False,
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
    if not bypass_rate_limit:
        limiter = get_publish_rate_limiter(
            min_interval_sec=settings.publish_channel_min_interval_sec,
            burst_window_sec=settings.publish_burst_window_sec,
            burst_max_messages=settings.publish_burst_max_messages,
        )
        await limiter.acquire_before_publish(int(chat_id))
    else:
        log_event(
            logger,
            "publish.rate_limit_bypassed",
            draft_id=draft_id,
            reason="operator_approved",
        )
    t_publish = time.perf_counter()
    html = build_channel_message_html(
        content,
        sources or "[]",
        draft_id=draft_id,
        include_sources=bool(getattr(settings, "publish_include_sources", False)),
        include_draft_id_footer=bool(getattr(settings, "publish_include_sources", False)),
    )
    from app.editorial.publish_pipeline_guards import enforce_publish_html_guards

    enforce_publish_html_guards(html, draft_id=draft_id, settings=settings)
    chunks = split_telegram_text(html, respect_html=True)
    from publisher.media_pipeline import publish_mode_for_extras

    publish_mode = publish_mode_for_extras(draft_extras_json)
    media = media_from_extras_json(
        draft_extras_json,
        include_fallback=_publish_fallback_media_enabled(),
    )
    if media and str(media.get("media_type") or "") == "video":
        adapted = await _maybe_adapt_video_for_publish(media=media, draft_id=draft_id)
        if adapted:
            media = adapted
        elif _video_strict_adapt_enabled():
            log_event(
                logger,
                "media.video_not_adapted_dropped",
                draft_id=draft_id,
                local_path=str(media.get("local_path") or ""),
            )
            media = None
    if media and Path(media["local_path"]).is_file():
        first_id = await _send_with_media(
            bot,
            chat_id=int(chat_id),
            media=media,
            chunks=chunks,
            draft_id=draft_id,
            settings=settings,
            publish_attempt=publish_attempt,
        )
        chunk_count = len(chunks) if chunks else 1
        log_event(
            logger,
            "publisher.media_sent",
            draft_id=draft_id,
            media_type=media.get("media_type"),
            chunk_count=chunk_count,
            channel_id=chat_id,
        )
        _record_publish_latency(t_publish, draft_extras_json)
        return first_id

    log_event(
        logger,
        "media.publish_mode",
        draft_id=draft_id,
        mode=publish_mode,
    )
    sent_ids = await _send_text_chunks(
        bot,
        chat_id=int(chat_id),
        chunks=chunks,
        draft_id=draft_id,
        settings=settings,
        publish_attempt=publish_attempt,
    )
    log_event(
        logger,
        "publisher.chunks_sent",
        draft_id=draft_id,
        chunk_count=len(sent_ids),
        channel_id=chat_id,
        duration_sec=round(time.perf_counter(), 4),
    )
    _record_publish_latency(t_publish, draft_extras_json)
    return sent_ids[0]


def _record_publish_latency(t_start: float, draft_extras_json: str | None) -> None:
    try:
        from app.observability.newsroom_ops import record_publish_latency_ms

        breaking = False
        if draft_extras_json:
            try:
                ex = json.loads(draft_extras_json)
                if isinstance(ex, dict):
                    brk = ex.get("breaking")
                    if isinstance(brk, dict):
                        breaking = bool(brk.get("is_breaking"))
            except (json.JSONDecodeError, TypeError):
                pass
        record_publish_latency_ms((time.perf_counter() - t_start) * 1000.0, breaking=breaking)
    except Exception:
        pass


# Spec / tests: stable name for the same entrypoint.
publish_draft = publish_draft_to_channel
