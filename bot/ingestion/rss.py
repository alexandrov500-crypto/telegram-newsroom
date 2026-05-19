from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from time import struct_time
from typing import Any

import feedparser

from bot.processing.media import MEDIA_NONE, MediaInfo, extract_rss_media

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    link: str
    published: datetime | None
    source: str
    media_type: str = MEDIA_NONE
    media_url: str | None = None
    thumbnail_url: str | None = None
    media_width: int | None = None
    media_height: int | None = None


def _parse_published(entry: Any) -> datetime | None:
    parsed: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch_feed_items(feed_url: str) -> list[NewsItem]:
    """Fetch and normalize entries from a single RSS/Atom feed URL."""
    parsed = feedparser.parse(feed_url)
    if getattr(parsed, "bozo", False) and getattr(parsed, "bozo_exception", None):
        logger.warning(
            "event=rss_parse_warning source=%r error=%r",
            feed_url,
            parsed.bozo_exception,
        )

    items: list[NewsItem] = []
    for entry in parsed.entries or []:
        link = str(entry.get("link", "")).strip()
        if not link:
            continue
        title = str(entry.get("title", "Untitled")).strip() or "Untitled"
        media = extract_rss_media(entry)
        items.append(
            NewsItem(
                title=title,
                link=link,
                published=_parse_published(entry),
                source=feed_url,
                media_type=media.media_type,
                media_url=media.media_url,
                thumbnail_url=media.thumbnail_url,
                media_width=media.width,
                media_height=media.height,
            )
        )
    return items
