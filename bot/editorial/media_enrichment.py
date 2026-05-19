from __future__ import annotations

import asyncio
import logging
import os

from bot.processing.media import (
    MEDIA_NONE,
    MEDIA_PHOTO,
    MediaInfo,
    choose_best_media,
    extract_og_image_from_html,
    validate_media,
    _candidate_from_url,
)
from bot.storage.editorial_repository import PendingNewsItem

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = float(os.getenv("EDITORIAL_MEDIA_TIMEOUT_SEC", "4.0"))
_MAX_BYTES = int(os.getenv("EDITORIAL_MEDIA_MAX_BYTES", "6000000"))
_USER_AGENT = "NewsroomAI/1.0 (+https://t.me/newsroom_ai_bot; editorial-preview)"


def _enrichment_enabled() -> bool:
    raw = os.getenv("EDITORIAL_MEDIA_ENRICH", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


async def fetch_opengraph_media(
    url: str,
    *,
    timeout_sec: float | None = None,
) -> MediaInfo:
    """Fetch article HTML and extract og:image. Never raises."""
    if not url or not url.startswith("http"):
        return MediaInfo.none()
    timeout = timeout_sec if timeout_sec is not None else _DEFAULT_TIMEOUT
    try:
        import httpx
    except ImportError:
        return MediaInfo.none()

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(2.0, timeout)),
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                return MediaInfo.none()
            if len(response.content) > _MAX_BYTES:
                logger.info("event=media_enrich_skipped reason=page_too_large url=%s", url[:80])
                return MediaInfo.none()
            html_text = response.text[:500_000]
    except Exception as exc:
        logger.debug("event=media_enrich_fetch_failed url=%s error=%s", url[:80], exc)
        return MediaInfo.none()

    og_url = extract_og_image_from_html(html_text)
    if not og_url:
        return MediaInfo.none()
    picked = _candidate_from_url(og_url, media_type=MEDIA_PHOTO, priority=25)
    if not picked:
        return MediaInfo.none()
    return validate_media(picked[1])


async def enrich_publish_media(item: PendingNewsItem) -> MediaInfo:
    """
    Resolve best media for publish: existing item fields, then OpenGraph fetch.
    Safe to call on publish path — bounded wait, no retries.
    """
    if not _enrichment_enabled():
        return _from_item(item)

    existing = _from_item(item)
    if existing.has_media:
        return existing

    link = (item.link or "").strip()
    if not link.startswith("http"):
        return MediaInfo.none()

    try:
        fetched = await asyncio.wait_for(
            fetch_opengraph_media(link),
            timeout=_DEFAULT_TIMEOUT + 0.5,
        )
    except asyncio.TimeoutError:
        logger.info("event=media_enrich_timeout pending_news_id=%s", item.id)
        return MediaInfo.none()
    except Exception:
        logger.debug("event=media_enrich_failed pending_news_id=%s", item.id)
        return MediaInfo.none()

    return choose_best_media(existing, fetched)


def _from_item(item: PendingNewsItem) -> MediaInfo:
    if item.media_type in (MEDIA_PHOTO, "photo", "video") and item.media_url:
        return validate_media(
            MediaInfo(
                media_type=item.media_type,
                media_url=item.media_url,
                thumbnail_url=item.thumbnail_url,
                width=item.media_width,
                height=item.media_height,
            ),
        )
    return MediaInfo.none()
