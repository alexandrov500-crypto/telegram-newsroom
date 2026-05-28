"""Read draft media attachment from draft_extras JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def media_from_extras_json(extras_json: str | None) -> dict[str, Any] | None:
    if not extras_json:
        return None
    try:
        ex = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(ex, dict):
        return None
    media = ex.get("media")
    if not isinstance(media, dict):
        return None
    media_type = str(media.get("media_type") or "").strip().lower()
    local_path = str(media.get("local_path") or "").strip()
    if media_type not in ("photo", "video") or not local_path:
        return None
    if not Path(local_path).is_file():
        return None
    return {
        "media_type": media_type,
        "local_path": local_path,
        "message_id": media.get("message_id"),
        "chat_id": media.get("chat_id"),
    }


def lead_media_from_raw_posts(posts: list[Any]) -> dict[str, Any] | None:
    """First post in cluster with a downloaded local photo/video."""
    for post in posts:
        extras = getattr(post, "extras", None)
        media = media_from_raw_post_extras(str(extras or "{}"))
        if media:
            return media
    return None


def media_from_raw_post_extras(extras_json: str | None) -> dict[str, Any] | None:
    """Same shape as draft extras `media` key, stored on raw_posts.extras."""
    if not extras_json:
        return None
    try:
        ex = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(ex, dict):
        return None
    media = ex.get("media")
    if isinstance(media, dict):
        return media_from_extras_json(json.dumps({"media": media}))
    return None
