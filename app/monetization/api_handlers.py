"""W5 B2B API + RSS HTTP handlers."""

from __future__ import annotations

import json
import os
from typing import Any

from app.monetization.asset_packaging import build_rss_feed, fetch_recent_published
from app.monetization.b2b_feed import (
    build_narratives_api,
    build_news_feed,
    build_signals_feed,
    build_source_reliability_index,
    check_rate_limit,
    validate_api_key,
)


def _w5_api_enabled() -> bool:
    return os.getenv("W5_B2B_API_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _rss_enabled() -> bool:
    return os.getenv("W5_RSS_FEED_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


async def dispatch_w5_http(
    path_only: str,
    query: dict[str, list[str]],
    headers: dict[str, str],
) -> tuple[int, str, bytes] | None:
    """Return (status, content_type, body) or None if not a W5 route."""

    if path_only == "/feed.xml" or path_only == "/export/rss":
        if not _rss_enabled():
            return 404, "application/json", b'{"error":"rss_disabled"}'
        limit = int((query.get("limit") or ["30"])[0])
        items = await fetch_recent_published(limit=min(50, limit))
        base = os.getenv("W5_RSS_CHANNEL_LINK", "https://t.me/")
        xml = build_rss_feed(items, base_url=base)
        return 200, "application/rss+xml; charset=utf-8", xml.encode("utf-8")

    if not path_only.startswith("/api/v1/"):
        return None

    if not _w5_api_enabled():
        return 503, "application/json", b'{"error":"b2b_api_disabled"}'

    api_key = validate_api_key(headers, query)
    expected = os.getenv("W5_B2B_API_KEY", "").strip()
    if expected and not api_key:
        return 403, "application/json", b'{"error":"forbidden"}'

    if api_key:
        rl = check_rate_limit(api_key)
        if not rl.allowed:
            return 429, "application/json", b'{"error":"rate_limited"}'

    limit = min(100, int((query.get("limit") or ["50"])[0]))

    if path_only == "/api/v1/feed":
        payload = await build_news_feed(limit=limit)
    elif path_only == "/api/v1/narratives":
        payload = await build_narratives_api()
    elif path_only == "/api/v1/signals":
        payload = await build_signals_feed(limit=limit)
    elif path_only == "/api/v1/sources/reliability":
        payload = await build_source_reliability_index()
    elif path_only == "/api/v1/health":
        payload = {"ok": True, "service": "newsroom-b2b-api", "version": "v1"}
    else:
        return 404, "application/json", b'{"error":"not_found"}'

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return 200, "application/json; charset=utf-8", body
