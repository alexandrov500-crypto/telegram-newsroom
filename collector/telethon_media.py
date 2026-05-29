"""Telethon message text + photo/video download for the newsroom collector."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.tl.custom.message import Message

logger = logging.getLogger(__name__)

MEDIA_NONE = "none"
MEDIA_PHOTO = "photo"
MEDIA_VIDEO = "video"

_WS = re.compile(r"\s+")


def message_plain_text(message: Message) -> str:
    """Caption or body text (Telethon uses `.message` for media captions)."""
    raw = getattr(message, "message", None) or getattr(message, "text", None) or ""
    return _WS.sub(" ", str(raw).strip())


def detect_media_type(message: Message) -> str:
    if getattr(message, "photo", None):
        return MEDIA_PHOTO
    if getattr(message, "video", None):
        return MEDIA_VIDEO
    doc = getattr(message, "document", None)
    if doc is not None:
        mime = (getattr(doc, "mime_type", None) or "").lower()
        if mime.startswith("image/") and "gif" not in mime:
            return MEDIA_PHOTO
        if mime.startswith("video/"):
            return MEDIA_VIDEO
    return MEDIA_NONE


def _cache_path(cache_dir: Path, *, chat_id: int, message_id: int, media_type: str) -> Path:
    ext = ".jpg" if media_type == MEDIA_PHOTO else ".mp4"
    safe_chat = re.sub(r"[^\w.-]", "_", str(chat_id))
    return cache_dir / f"{safe_chat}_{message_id}{ext}"


def _video_dimensions(message: Message) -> tuple[int | None, int | None, int | None]:
    video = getattr(message, "video", None)
    if video is not None:
        w = getattr(video, "w", None) or getattr(video, "width", None)
        h = getattr(video, "h", None) or getattr(video, "height", None)
        dur = getattr(video, "duration", None)
        return (
            int(w) if w else None,
            int(h) if h else None,
            int(dur) if dur else None,
        )
    doc = getattr(message, "document", None)
    if doc is not None:
        for attr in getattr(doc, "attributes", None) or []:
            cls = type(attr).__name__
            if cls == "DocumentAttributeVideo":
                w = getattr(attr, "w", None)
                h = getattr(attr, "h", None)
                dur = getattr(attr, "duration", None)
                return (
                    int(w) if w else None,
                    int(h) if h else None,
                    int(dur) if dur else None,
                )
    return None, None, None


async def download_message_media(
    client: TelegramClient,
    message: Message,
    cache_dir: Path,
) -> dict[str, Any] | None:
    """Download photo/video to cache_dir; return extras payload or None."""
    media_type = detect_media_type(message)
    if media_type == MEDIA_NONE:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    chat_id = int(getattr(message, "chat_id", 0) or 0)
    msg_id = int(getattr(message, "id", 0) or 0)
    dest = _cache_path(cache_dir, chat_id=chat_id, message_id=msg_id, media_type=media_type)
    try:
        path = await client.download_media(message, file=str(dest))
    except Exception as exc:
        logger.warning("collector.media_download_failed msg=%s err=%s", msg_id, exc)
        return None
    if not path:
        return None
    local = Path(path)
    if not local.is_file() or local.stat().st_size < 512:
        return None
    payload: dict[str, Any] = {
        "media_type": media_type,
        "local_path": str(local.resolve()),
        "message_id": msg_id,
        "chat_id": chat_id,
    }
    if media_type == MEDIA_VIDEO:
        w, h, dur = _video_dimensions(message)
        if w:
            payload["width"] = w
        if h:
            payload["height"] = h
        if dur:
            payload["duration"] = dur
    return payload
