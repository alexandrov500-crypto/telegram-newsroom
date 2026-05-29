"""Read draft media attachment from draft_extras JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def media_from_extras_json(
    extras_json: str | None,
    *,
    include_fallback: bool = False,
) -> dict[str, Any] | None:
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
    if not include_fallback and (
        media.get("media_fallback_used")
        or str(media.get("media_status") or "").strip().lower() == "fallback_generated"
    ):
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
        "width": media.get("width"),
        "height": media.get("height"),
        "duration": media.get("duration"),
    }


def lead_media_from_raw_posts(posts: list[Any]) -> dict[str, Any] | None:
    """First post in cluster with a downloaded local photo/video."""
    for post in posts:
        extras = getattr(post, "extras", None)
        media = media_from_raw_post_extras(str(extras or "{}"))
        if media:
            return media
    return None


def lead_media_from_collector_cache(
    posts: list[Any],
    cache_root: Path,
) -> dict[str, Any] | None:
    """Resolve Telethon-downloaded media from collector cache when extras were not persisted."""
    if not cache_root.is_dir():
        return None
    for post in posts:
        message_id = getattr(post, "message_id", None)
        if message_id is None:
            continue
        try:
            msg_id = int(message_id)
        except (TypeError, ValueError):
            continue
        for ext, media_type in ((".jpg", "photo"), (".mp4", "video")):
            matches = sorted(cache_root.glob(f"*_{msg_id}{ext}"))
            for path in matches:
                if not path.is_file() or path.stat().st_size < 512:
                    continue
                if media_type == "photo":
                    from publisher.media_cache import validate_local_image

                    if not validate_local_image(path):
                        continue
                chat_id = _chat_id_from_cache_name(path.name, msg_id)
                return {
                    "media_type": media_type,
                    "local_path": str(path.resolve()),
                    "message_id": msg_id,
                    "chat_id": chat_id,
                }
    return None


def _chat_id_from_cache_name(filename: str, message_id: int) -> int | None:
    suffix = f"_{message_id}"
    stem = filename.rsplit(".", 1)[0]
    if not stem.endswith(suffix):
        return None
    chat_part = stem[: -len(suffix)]
    if not chat_part:
        return None
    try:
        return int(chat_part)
    except ValueError:
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
