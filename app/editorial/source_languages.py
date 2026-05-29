"""Source / output language resolution for multilingual Telegram ingest (zh → ru)."""

from __future__ import annotations

import os
import re
from typing import Any

LANG_RU = "ru"
LANG_EN = "en"
LANG_ZH = "zh"

SUPPORTED_LANGUAGES = frozenset({LANG_RU, LANG_EN, LANG_ZH})

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def normalize_language_code(raw: str | None) -> str | None:
    if not raw:
        return None
    code = str(raw).strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED_LANGUAGES else None


def normalize_channel_handle(channel: str) -> str:
    ch = (channel or "").strip()
    if not ch:
        return ""
    return ch if ch.startswith("@") else f"@{ch.lstrip('@')}"


def parse_source_channel_languages(raw: str | None = None) -> dict[str, str]:
    """Parse SOURCE_CHANNEL_LANGUAGES=@tnews365:zh,@cb_economics:ru."""
    text = (raw if raw is not None else os.getenv("SOURCE_CHANNEL_LANGUAGES", "")).strip()
    out: dict[str, str] = {}
    if not text:
        return out
    for part in text.replace(";", ",").split(","):
        chunk = part.strip()
        if not chunk or ":" not in chunk:
            continue
        channel, lang = chunk.split(":", 1)
        handle = normalize_channel_handle(channel)
        code = normalize_language_code(lang)
        if handle and code:
            out[handle.lower()] = code
    return out


def publish_output_language(settings: Any | None = None) -> str:
    if settings is not None:
        code = normalize_language_code(getattr(settings, "publish_output_language", None))
        if code:
            return code
    return normalize_language_code(os.getenv("PUBLISH_OUTPUT_LANGUAGE", LANG_RU)) or LANG_RU


def language_for_channel(channel: str, *, settings: Any | None = None) -> str | None:
    handle = normalize_channel_handle(channel)
    if not handle:
        return None
    mapping: dict[str, str] = {}
    if settings is not None:
        mapping = dict(getattr(settings, "source_channel_languages", {}) or {})
    if not mapping:
        mapping = parse_source_channel_languages()
    return mapping.get(handle.lower())


def detect_text_language(text: str) -> str:
    """Heuristic detect ru / zh / en from Unicode ranges."""
    blob = (text or "").strip()
    if not blob:
        return LANG_EN
    cjk = len(_CJK_RE.findall(blob))
    cyr = len(_CYRILLIC_RE.findall(blob))
    lat = len(_LATIN_RE.findall(blob))
    if cjk >= max(8, cyr * 2, lat):
        return LANG_ZH
    if cyr >= max(8, lat // 2):
        return LANG_RU
    return LANG_EN


def cluster_source_language(posts: list[Any], settings: Any | None = None) -> str:
    """Best-effort source language for a cluster (configured channel lang wins)."""
    langs: list[str] = []
    for post in posts:
        channel = str(getattr(post, "channel_name", "") or "")
        configured = language_for_channel(channel, settings=settings)
        if configured:
            langs.append(configured)
            continue
        extras_raw = getattr(post, "extras", None) or "{}"
        try:
            import json

            ex = json.loads(str(extras_raw))
            if isinstance(ex, dict):
                sl = normalize_language_code(str(ex.get("source_language") or ""))
                if sl:
                    langs.append(sl)
                    continue
        except (json.JSONDecodeError, TypeError):
            pass
        langs.append(detect_text_language(str(getattr(post, "text", "") or "")))
    if not langs:
        return LANG_RU
    if LANG_ZH in langs:
        return LANG_ZH
    if all(x == LANG_EN for x in langs):
        return LANG_EN
    return LANG_RU


def requires_translation(source_language: str, output_language: str) -> bool:
    src = normalize_language_code(source_language) or LANG_RU
    out = normalize_language_code(output_language) or LANG_RU
    return src != out


def cjk_ratio(text: str) -> float:
    blob = (text or "").strip()
    if not blob:
        return 0.0
    cjk = len(_CJK_RE.findall(blob))
    return cjk / max(len(blob), 1)


def text_violates_output_language(text: str, *, output_language: str) -> bool:
    """Block RU publish if CJK characters leak into final body."""
    out = normalize_language_code(output_language) or LANG_RU
    if out != LANG_RU:
        return False
    return cjk_ratio(text) >= 0.03


def translation_context_for_cluster(
    posts: list[Any],
    settings: Any | None = None,
) -> dict[str, str]:
    src = cluster_source_language(posts, settings)
    out = publish_output_language(settings)
    return {
        "source_language": src,
        "output_language": out,
        "translation_required": requires_translation(src, out),
    }
