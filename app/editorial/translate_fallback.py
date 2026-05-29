"""zh→ru translation when OpenAI is unavailable (VPS region / circuit open)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
import httpx

from app.editorial.source_languages import (
    LANG_ZH,
    cjk_ratio,
    cluster_source_language,
    publish_output_language,
    requires_translation,
    text_violates_output_language,
)
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_CHUNK_MAX = 420
_SENT_SPLIT = re.compile(r"(?<=[。！？.!?])\s*")


def _enabled() -> bool:
    return os.getenv("ZH_TRANSLATE_FALLBACK_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _chunk_text(text: str, *, max_len: int = _CHUNK_MAX) -> list[str]:
    blob = (text or "").strip()
    if not blob:
        return []
    if len(blob) <= max_len:
        return [blob]
    parts = [p.strip() for p in _SENT_SPLIT.split(blob) if p.strip()]
    if not parts:
        return [blob[i : i + max_len] for i in range(0, len(blob), max_len)]
    chunks: list[str] = []
    buf = ""
    for part in parts:
        candidate = f"{buf}{part}" if not buf else f"{buf} {part}"
        if len(candidate) <= max_len:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        buf = part if len(part) <= max_len else part[:max_len]
    if buf:
        chunks.append(buf)
    return chunks or [blob[:max_len]]


async def _mymemory_translate(chunk: str, *, timeout: float) -> str | None:
    url = "https://api.mymemory.translated.net/get"
    params = {"q": chunk, "langpair": "zh|ru"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log_event(logger, "translate_fallback.mymemory_failed", error=repr(exc)[:200])
        return None
    if not isinstance(data, dict):
        return None
    block = data.get("responseData")
    if not isinstance(block, dict):
        return None
    out = str(block.get("translatedText") or "").strip()
    if not out or out.upper() == chunk.upper():
        return None
    return out


async def _libretranslate(chunk: str, *, base_url: str, timeout: float) -> str | None:
    endpoint = base_url.rstrip("/") + "/translate"
    payload = {"q": chunk, "source": "zh", "target": "ru", "format": "text"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log_event(logger, "translate_fallback.libre_failed", error=repr(exc)[:200])
        return None
    if isinstance(data, dict) and data.get("translatedText"):
        return str(data["translatedText"]).strip()
    return None


async def translate_zh_to_ru(text: str, *, timeout: float | None = None) -> str | None:
    """
    Best-effort Chinese → Russian for newsroom publish path.
    Returns None if translation unavailable or output still looks Chinese.
    """
    if not _enabled():
        return None
    src = (text or "").strip()
    if not src or cjk_ratio(src) < 0.08:
        return src if src else None
    tmo = float(timeout if timeout is not None else os.getenv("ZH_TRANSLATE_TIMEOUT_SEC", "25"))
    libre = os.getenv("LIBRETRANSLATE_URL", "").strip()
    pieces: list[str] = []
    for chunk in _chunk_text(src):
        translated: str | None = None
        if libre:
            translated = await _libretranslate(chunk, base_url=libre, timeout=tmo)
        if not translated:
            translated = await _mymemory_translate(chunk, timeout=tmo)
        if not translated:
            return None
        pieces.append(translated)
    out = " ".join(pieces).strip()
    if not out or text_violates_output_language(out, output_language="ru"):
        return None
    log_event(logger, "translate_fallback.ok", chars_in=len(src), chars_out=len(out))
    return out


def posts_with_translated_text(posts: list[Any], translated_by_id: dict[int, str]) -> list[Any]:
    """Shallow copy posts with replaced .text for summarization."""
    from types import SimpleNamespace

    out: list[Any] = []
    for p in posts:
        pid = getattr(p, "id", None)
        text = translated_by_id.get(int(pid)) if pid is not None else None
        if text is None:
            text = str(getattr(p, "text", "") or "")
        out.append(
            SimpleNamespace(
                id=getattr(p, "id", None),
                channel_name=getattr(p, "channel_name", ""),
                message_id=getattr(p, "message_id", 0),
                text=text,
                extras=getattr(p, "extras", "{}"),
                created_at=getattr(p, "created_at", None),
                collected_at=getattr(p, "collected_at", None),
                processed_at=getattr(p, "processed_at", None),
            )
        )
    return out


async def translate_cluster_posts(posts: list[Any], settings: Any) -> list[Any] | None:
    """Return cluster posts with RU text when zh→ru translation is required."""
    src = cluster_source_language(posts, settings)
    out_lang = publish_output_language(settings)
    if not requires_translation(src, out_lang):
        return list(posts)
    if src != LANG_ZH:
        return None
    translated: dict[int, str] = {}
    for p in posts:
        pid = getattr(p, "id", None)
        if pid is None:
            continue
        raw = str(getattr(p, "text", "") or "")
        if not raw.strip():
            continue
        if not text_violates_output_language(raw, output_language=out_lang):
            translated[int(pid)] = raw
            continue
        ru = await translate_zh_to_ru(raw)
        if not ru:
            return None
        translated[int(pid)] = ru
    if not translated:
        return None
    return posts_with_translated_text(posts, translated)
