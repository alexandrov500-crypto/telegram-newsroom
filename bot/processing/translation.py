from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass

from bot.config import bootstrap_env, get_openai_api_key, get_openai_model
from bot.observability.metrics import record_openai_usage, record_translation_failure
from bot.processing.languages import (
    DEFAULT_SOURCE_LANGUAGE,
    LANG_EN,
    LANG_RU,
    normalize_language_code,
)

logger = logging.getLogger(__name__)

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

_STATIC_LOCALIZED_HEADLINES: dict[tuple[str, str], str] = {
    ("SEC approves Bitcoin ETF", LANG_RU): "SEC официально одобрила Bitcoin ETF",
}

_STATIC_HOOKS: dict[str, str] = {
    LANG_RU: "📈 Рынки реагируют",
    LANG_EN: "📈 Markets react",
}


@dataclass(frozen=True, slots=True)
class LocalizedStory:
    language: str
    title: str
    summary: str
    headline: str
    hook: str
    translated: bool


def _sanitize_unicode(text: str) -> str:
    try:
        return unicodedata.normalize("NFKC", text).strip()
    except Exception:
        return str(text).strip()


def detect_language(text: str) -> str:
    """Heuristic language detection (RU / EN). Fail-open to English."""
    try:
        blob = _sanitize_unicode(text)
        if not blob:
            return DEFAULT_SOURCE_LANGUAGE
        if _CYRILLIC_RE.search(blob):
            return LANG_RU
        return LANG_EN
    except Exception:
        logger.exception("event=translation_failed action=detect_language")
        return DEFAULT_SOURCE_LANGUAGE


def _static_headline(title: str, target_lang: str) -> str | None:
    return _STATIC_LOCALIZED_HEADLINES.get((title.strip(), target_lang))


async def translate_story(
    title: str,
    summary: str | None,
    *,
    source_lang: str,
    target_lang: str,
) -> tuple[str, str]:
    """Translate title and summary. Preserves meaning; falls back to source text."""
    source = normalize_language_code(source_lang) or DEFAULT_SOURCE_LANGUAGE
    target = normalize_language_code(target_lang) or DEFAULT_SOURCE_LANGUAGE
    safe_title = _sanitize_unicode(title)[:500]
    safe_summary = _sanitize_unicode(summary or "")[:4000]

    if source == target or not safe_title:
        return safe_title, safe_summary

    static = _static_headline(safe_title, target)
    if static is not None:
        logger.info(
            "event=translation_generated source=%s target=%s mode=static",
            source,
            target,
        )
        return static, safe_summary

    api_key = get_openai_api_key()
    if not api_key:
        logger.info(
            "event=translation_generated source=%s target=%s mode=fallback",
            source,
            target,
        )
        return safe_title, safe_summary

    try:
        from openai import AsyncOpenAI

        bootstrap_env()
        client = AsyncOpenAI(api_key=api_key)
        prompt = (
            f"Translate the news story from {source} to {target}. "
            "Preserve all facts exactly; do not add or remove claims. "
            "Use natural newsroom tone for Telegram readers in the target region. "
            "Return JSON: {\"title\": \"...\", \"summary\": \"...\"}"
        )
        user = json.dumps(
            {"title": safe_title, "summary": safe_summary},
            ensure_ascii=False,
        )
        response = await client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            record_openai_usage(
                operation="translation",
                model=get_openai_model(),
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                success=True,
            )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        out_title = _sanitize_unicode(str(parsed.get("title") or safe_title))[:500]
        out_summary = _sanitize_unicode(str(parsed.get("summary") or safe_summary))[:4000]
        if not out_title:
            out_title = safe_title
        logger.info(
            "event=translation_generated source=%s target=%s mode=openai",
            source,
            target,
        )
        return out_title, out_summary
    except Exception:
        record_translation_failure()
        record_openai_usage(
            operation="translation",
            model=get_openai_model(),
            prompt_tokens=0,
            completion_tokens=0,
            success=False,
        )
        logger.exception(
            "event=translation_failed source=%s target=%s",
            source,
            target,
        )
        return safe_title, safe_summary


async def localize_headline(
    title: str,
    *,
    target_lang: str,
    summary: str | None = None,
) -> str:
    """Editorial headline for Telegram (not word-for-word). Fail-open to title."""
    target = normalize_language_code(target_lang) or LANG_EN
    safe = _sanitize_unicode(title)[:500]
    if not safe:
        return safe

    static = _static_headline(safe, target)
    if static is not None:
        logger.info("event=localization_applied field=headline lang=%s mode=static", target)
        return static

    api_key = get_openai_api_key()
    if not api_key:
        return safe

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Rewrite this headline for a {target} Telegram news channel. "
                        "Keep facts identical. Optimize urgency, rhythm, and local readability. "
                        "Return only the headline text, no quotes."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"headline": safe, "summary": summary or ""},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.35,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            record_openai_usage(
                operation="localize_headline",
                model=get_openai_model(),
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                success=True,
            )
        out = _sanitize_unicode((response.choices[0].message.content or safe))[:240]
        logger.info("event=localization_applied field=headline lang=%s mode=openai", target)
        return out or safe
    except Exception:
        record_translation_failure()
        logger.exception("event=translation_failed action=localize_headline lang=%s", target)
        return safe


async def localize_hook(
    hook: str | None,
    *,
    target_lang: str,
    title: str | None = None,
) -> str:
    """Localized hook line for Telegram caption."""
    target = normalize_language_code(target_lang) or LANG_EN
    base = _sanitize_unicode(hook or "")[:120]
    if not base:
        return _STATIC_HOOKS.get(target, _STATIC_HOOKS[LANG_EN])

    if base in _STATIC_HOOKS.values() and target in _STATIC_HOOKS:
        logger.info("event=localization_applied field=hook lang=%s mode=static", target)
        return _STATIC_HOOKS[target]

    api_key = get_openai_api_key()
    if not api_key:
        return _STATIC_HOOKS.get(target, base)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Adapt this Telegram hook for {target} readers. "
                        "One short line, may include one emoji, same factual angle. "
                        "Return only the hook."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"hook": base, "headline": title or ""},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.4,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            record_openai_usage(
                operation="localize_hook",
                model=get_openai_model(),
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                success=True,
            )
        out = _sanitize_unicode((response.choices[0].message.content or base))[:120]
        logger.info("event=localization_applied field=hook lang=%s mode=openai", target)
        return out or _STATIC_HOOKS.get(target, base)
    except Exception:
        record_translation_failure()
        logger.exception("event=translation_failed action=localize_hook lang=%s", target)
        return _STATIC_HOOKS.get(target, base)


async def build_localized_story(
    *,
    title: str,
    summary: str | None,
    hook: str | None,
    source_lang: str,
    target_lang: str,
) -> LocalizedStory:
    """Full localization pipeline for one target language."""
    target = normalize_language_code(target_lang) or LANG_EN
    translated_title, translated_summary = await translate_story(
        title,
        summary,
        source_lang=source_lang,
        target_lang=target,
    )
    headline = await localize_headline(
        translated_title,
        target_lang=target,
        summary=translated_summary,
    )
    localized_hook = await localize_hook(
        hook,
        target_lang=target,
        title=headline,
    )
    return LocalizedStory(
        language=target,
        title=translated_title,
        summary=translated_summary,
        headline=headline,
        hook=localized_hook,
        translated=target != (normalize_language_code(source_lang) or LANG_EN),
    )


def target_languages_for_publish(
    source_lang: str,
    enabled: set[str],
) -> list[str]:
    """Enabled publish languages in stable display order."""
    _ = source_lang
    from bot.processing.languages import SUPPORTED_LANGUAGES

    return [code for code in SUPPORTED_LANGUAGES if code in enabled]
