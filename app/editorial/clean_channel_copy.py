"""Clean publish copy — cb_economics-style finished posts (no pipeline filler)."""

from __future__ import annotations

import os
import re

from app.editorial.cb_brief_format import cb_brief_format_enabled, compose_cb_brief_text

_BOILERPLATE_WHY = re.compile(
    r"\n?\n?Почему\s+(?:это\s+)?важно\s*:\s*"
    r"(?:событие\s+меняет\s+контекст|событие\s+влияет\s+на\s+решения|"
    r"меняет\s+расчёт\s+риска)[^.!?]*[.!?]?\s*",
    re.I,
)
_BOILERPLATE_NEXT = re.compile(
    r"\n?\n?Что\s+дальше\s*:\s*следим\s+за\s+подтверждением[^.!?]*[.!?]?\s*",
    re.I,
)
_AUH_CONTEXT = re.compile(
    r"\n?\n?(?:Геополитический\s+контекст|Связь\s+с\s+геополитикой|"
    r"Компании\s+пересматривают\s+стратегии|Рынки\s+уже\s+закладывают|"
    r"Технологический\s+сектор\s+реагирует)[^.!?]*[.!?]?\s*",
    re.I,
)
_VIDEO_TEASER = re.compile(
    r"\n?\n?🐚?\s*Если\s+у\s+вас\s+не\s+загружается\s+видео[^.!?]*[.!?]?\s*",
    re.I,
)
_PLACEHOLDER_SQUARES = re.compile(r"[◻️⬜️\u25FB]\s*")
_BULLET_PLAY = re.compile(r"[\u25B6\u25B7▶]\uFE0F?\s*")
_HASHTAG_LINE = re.compile(r"^\s*(?:#[\w\u0400-\u04FF]+\s*)+$", re.M)
_INLINE_HASHTAGS = re.compile(r"\s+(?:#[\w\u0400-\u04FF]+\s*){1,6}\s*$")
_LABEL_BLOCK = re.compile(
    r"^\s*(?:⚡\s*Что\s+произошло|📊\s*Почему\s+это\s+важно|"
    r"💰\s*Что\s+это\s+значит|🎯\s*Что\s+будет\s+дальше)\s*$",
    re.I | re.M,
)


def clean_channel_copy_enabled() -> bool:
    if not cb_brief_format_enabled():
        return False
    raw = os.getenv("NEWSROOM_CLEAN_CHANNEL_COPY", "true").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled
        from app.editorial.reference_model import reference_model_enabled

        if news_channel_beat_enabled() or reference_model_enabled():
            return True
    except Exception:
        pass
    return raw in {"1", "true", "yes", "on", ""}


def _strip_publish_chrome_preserve_paragraphs(text: str) -> str:
    """Strip growth chrome without collapsing paragraph breaks."""
    from app.editorial.content_quality import (
        _BRAND_CTA,
        _CONTINUATION_SERIES,
        _ENGAGEMENT_HOOK,
        _OPEN_LOOP,
        _TRAILING_HASHTAGS,
        strip_editorial_template_noise,
    )

    t = strip_editorial_template_noise(text or "")
    for pattern in (_CONTINUATION_SERIES, _ENGAGEMENT_HOOK, _OPEN_LOOP, _BRAND_CTA):
        t = pattern.sub("", t)
    t = _TRAILING_HASHTAGS.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def scrub_editorial_pipeline_filler(text: str) -> str:
    """Remove growth/MPAES/AUH boilerplate and draft chrome."""
    t = _strip_publish_chrome_preserve_paragraphs(text or "")
    for _ in range(4):
        prev = t
        t = _BOILERPLATE_WHY.sub("\n", t)
        t = _BOILERPLATE_NEXT.sub("\n", t)
        t = _AUH_CONTEXT.sub("\n", t)
        t = _VIDEO_TEASER.sub("\n", t)
        t = _LABEL_BLOCK.sub("", t)
        if t == prev:
            break
    t = _PLACEHOLDER_SQUARES.sub("", t)
    t = _BULLET_PLAY.sub("", t)
    t = _HASHTAG_LINE.sub("", t)
    t = _INLINE_HASHTAGS.sub("", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", t):
        block = re.sub(r"\s+", " ", block.replace("\n", " ")).strip()
        if block:
            paragraphs.append(block)
    return "\n\n".join(paragraphs)


def prepare_clean_channel_post(text: str, *, max_chars: int = 2800) -> str:
    """Finished channel post: scrub pipeline filler → cb_economics brief shape."""
    if not clean_channel_copy_enabled():
        return (text or "").strip()
    cleaned = scrub_editorial_pipeline_filler(text)
    if not cleaned:
        return ""
    return compose_cb_brief_text(cleaned, max_chars=max_chars)
