from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from bot.config import bootstrap_env, get_openai_api_key, get_openai_model
from bot.processing.adaptive import pick_adaptive_hook

logger = logging.getLogger(__name__)

STYLE_SHORT = "short"
STYLE_MEDIUM = "medium"
STYLE_LONG = "long"

CAPTION_ORIGINAL = "original"
CAPTION_OPTIMIZED = "optimized"
CAPTION_HYBRID = "hybrid"

_LENGTH_LIMITS = {
    STYLE_SHORT: 80,
    STYLE_MEDIUM: 140,
    STYLE_LONG: 240,
}

_LLM_TIMEOUT_SEC = 15.0
_MAX_ATTEMPTS = 2
_TEMPERATURE = 0.25

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F600-\U0001F64F"
    "]+",
    flags=re.UNICODE,
)
_MARKDOWN_RE = re.compile(r"[*_`#>\[\]]+")

_SYSTEM_PROMPT = (
    "You are a Telegram newsroom editor. Write factual, engaging headlines. "
    "Never invent facts, numbers, or claims not supported by the input. "
    "No clickbait lies, no misinformation, no sensationalism. "
    "Use at most one emoji only in hook_line when appropriate."
)

_USER_PROMPT = """Rewrite this story for Telegram engagement.

Original title: {title}
Summary: {summary}
Tags: {tags}
Key entities: {entities}
Headline length mode: {mode} (max {max_len} characters for headline)

Goals: clarity, curiosity, urgency, relevance, readability — without hype or false claims.
Use entity names naturally when relevant (e.g. "OpenAI launches...", "SEC approves...").

Return STRICT JSON only:
{{
  "headline": "...",
  "hook_line": "..." or null,
  "short_caption": "...",
  "long_caption": "..."
}}

Rules:
- headline: single line, <= {max_len} chars, no emojis in headline
- hook_line: optional concise Telegram hook (<= 48 chars), may use one emoji prefix like 🔥 ⚠️ 📈
- short_caption: 1 sentence teaser <= 160 chars
- long_caption: 1-2 factual sentences <= 320 chars
"""


@dataclass(frozen=True, slots=True)
class HeadlineResult:
    optimized_headline: str
    hook_line: str | None
    short_caption: str
    long_caption: str
    headline_mode: str
    used_fallback: bool = False


def _sanitize(value: str, *, max_len: int | None = None) -> str:
    text = _MARKDOWN_RE.sub("", value)
    text = _EMOJI_RE.sub("", text)
    text = " ".join(text.split())
    if max_len is not None and len(text) > max_len:
        cut = text[:max_len].rsplit(" ", 1)[0]
        text = (cut.rstrip(".,;:") + "…") if cut else text[:max_len]
    return text.strip()


def _truncate(value: str, max_len: int) -> str:
    text = _sanitize(value, max_len=max_len)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _entity_names(entities: list[str] | None) -> list[str]:
    if not entities:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for raw in entities:
        name = str(raw).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names[:6]


def _rule_hook(title: str, summary: str, entities: list[str]) -> str | None:
    blob = f"{title} {summary} {' '.join(entities)}".lower()
    if any(token in blob for token in ("hack", "breach", "security", "vulnerability", "exploit")):
        return "⚠️ Security incident"
    if any(token in blob for token in ("sec", "regulation", "regulator", "lawsuit", "ban")):
        return "⚠️ Regulatory update"
    if any(token in blob for token in ("bitcoin", "ethereum", "crypto", "etf", "token")):
        return "📈 Markets react"
    if any(token in blob for token in ("openai", "anthropic", "gpt", " ai ", "artificial intelligence")):
        return "🔥 Major AI update"
    if any(token in blob for token in ("startup", "funding", "series a", "venture")):
        return "🚀 Startup news"
    return None


def _rule_headline(title: str, entities: list[str], *, mode: str) -> str:
    limit = _LENGTH_LIMITS.get(mode, _LENGTH_LIMITS[STYLE_MEDIUM])
    clean = _sanitize(title)
    names = _entity_names(entities)
    if names and names[0].lower() not in clean.lower():
        candidate = f"{names[0]}: {clean}"
    else:
        candidate = clean
    return _truncate(candidate, limit)


def _rule_short_caption(summary: str) -> str:
    return _truncate(summary or "", 160)


def _rule_long_caption(summary: str) -> str:
    return _truncate(summary or "", 320)


def generate_optimized_headline(
    *,
    title: str,
    summary: str,
    entities: list[str] | None = None,
    mode: str = STYLE_MEDIUM,
) -> str:
    return _rule_headline(title, _entity_names(entities), mode=mode)


def generate_hook_line(
    *,
    title: str,
    summary: str,
    entities: list[str] | None = None,
    tags: list[str] | None = None,
    hook_signals: list[tuple[str, float]] | None = None,
) -> str | None:
    _ = tags
    rule_hook = _rule_hook(title, summary, _entity_names(entities))
    hook = pick_adaptive_hook(rule_hook, hook_signals or [])
    if hook:
        logger.info("event=hook_generated hook=%r", hook)
    return hook


def generate_short_caption(*, summary: str, headline: str | None = None) -> str:
    _ = headline
    return _rule_short_caption(summary)


def generate_long_caption(*, summary: str, headline: str | None = None) -> str:
    _ = headline
    return _rule_long_caption(summary)


def _parse_llm_payload(content: str, *, title: str, mode: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    limit = _LENGTH_LIMITS.get(mode, _LENGTH_LIMITS[STYLE_MEDIUM])
    headline = _sanitize(str(data.get("headline") or title), max_len=limit)
    if not headline:
        headline = _rule_headline(title, [], mode=mode)
    hook_raw = data.get("hook_line")
    hook = None
    if hook_raw is not None and str(hook_raw).strip():
        hook = str(hook_raw).strip()[:48]
    short_cap = _sanitize(str(data.get("short_caption") or ""), max_len=160)
    long_cap = _sanitize(str(data.get("long_caption") or short_cap), max_len=320)
    if not short_cap:
        short_cap = _rule_short_caption(title)
    if not long_cap:
        long_cap = _rule_long_caption(title)
    return {
        "headline": headline,
        "hook_line": hook,
        "short_caption": short_cap,
        "long_caption": long_cap,
    }


async def _llm_optimize(
    *,
    title: str,
    summary: str,
    tags: list[str],
    entities: list[str],
    mode: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    client = AsyncOpenAI(api_key=api_key, timeout=_LLM_TIMEOUT_SEC, max_retries=0)
    max_len = _LENGTH_LIMITS.get(mode, _LENGTH_LIMITS[STYLE_MEDIUM])
    prompt = _USER_PROMPT.format(
        title=title,
        summary=summary or title,
        tags=", ".join(tags) if tags else "(none)",
        entities=", ".join(entities) if entities else "(none)",
        mode=mode,
        max_len=max_len,
    )

    async def _request() -> Any:
        return await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=_TEMPERATURE,
            max_tokens=220,
        )

    last_error: BaseException | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = await asyncio.wait_for(_request(), timeout=_LLM_TIMEOUT_SEC)
            content = response.choices[0].message.content
            if not content:
                raise ValueError("empty response")
            return _parse_llm_payload(content, title=title, mode=mode)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < _MAX_ATTEMPTS:
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("headline LLM exhausted")


def _build_result(
    *,
    title: str,
    summary: str,
    tags: list[str],
    entities: list[str] | None,
    mode: str,
    payload: dict[str, Any] | None,
    used_fallback: bool,
    hook_signals: list[tuple[str, float]] | None = None,
) -> HeadlineResult:
    names = _entity_names(entities)
    if payload:
        optimized = str(payload["headline"])
        hook = pick_adaptive_hook(payload.get("hook_line"), hook_signals or [])
        short_cap = str(payload.get("short_caption") or _rule_short_caption(summary))
        long_cap = str(payload.get("long_caption") or _rule_long_caption(summary))
    else:
        optimized = _rule_headline(title, names, mode=mode)
        hook = generate_hook_line(
            title=title,
            summary=summary,
            entities=names,
            hook_signals=hook_signals,
        )
        short_cap = _rule_short_caption(summary)
        long_cap = _rule_long_caption(summary)

    if hook:
        logger.info("event=hook_generated hook=%r", hook)
    logger.info(
        "event=headline_generated mode=%s fallback=%s headline=%r",
        mode,
        used_fallback,
        optimized[:80],
    )
    if used_fallback:
        logger.info("event=headline_fallback_used title=%r", title[:80])

    return HeadlineResult(
        optimized_headline=optimized,
        hook_line=hook,
        short_caption=short_cap,
        long_caption=long_cap,
        headline_mode=mode,
        used_fallback=used_fallback,
    )


async def optimize_story_headlines(
    *,
    title: str,
    summary: str,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    mode: str = STYLE_MEDIUM,
    use_llm: bool = True,
    hook_signals: list[tuple[str, float]] | None = None,
) -> HeadlineResult:
    """Generate engagement-optimized headlines. Never raises."""
    bootstrap_env()
    tag_list = list(tags or [])
    entity_list = _entity_names(entities)
    safe_title = _sanitize(title) or "News update"
    safe_summary = _sanitize(summary or safe_title)

    if not use_llm:
        return _build_result(
            title=safe_title,
            summary=safe_summary,
            tags=tag_list,
            entities=entity_list,
            mode=mode,
            payload=None,
            used_fallback=True,
            hook_signals=hook_signals,
        )

    api_key = get_openai_api_key()
    if not api_key:
        return _build_result(
            title=safe_title,
            summary=safe_summary,
            tags=tag_list,
            entities=entity_list,
            mode=mode,
            payload=None,
            used_fallback=True,
            hook_signals=hook_signals,
        )

    model = get_openai_model()
    try:
        from bot.cognitive.integrations import route_for_operation

        route = route_for_operation("headline", importance_score=0.5, qos_class="publish")
        if route is not None:
            model = route.model if route.model != "local" else model
    except Exception:
        pass

    try:
        payload = await _llm_optimize(
            title=safe_title,
            summary=safe_summary,
            tags=tag_list,
            entities=entity_list,
            mode=mode,
            api_key=api_key,
            model=model,
        )
        return _build_result(
            title=safe_title,
            summary=safe_summary,
            tags=tag_list,
            entities=entity_list,
            mode=mode,
            payload=payload,
            used_fallback=False,
            hook_signals=hook_signals,
        )
    except Exception:
        logger.warning("event=headline_fallback_used reason=llm_error")
        return _build_result(
            title=safe_title,
            summary=safe_summary,
            tags=tag_list,
            entities=entity_list,
            mode=mode,
            payload=None,
            used_fallback=True,
            hook_signals=hook_signals,
        )


def resolve_publish_headline(
    *,
    original_title: str,
    optimized_headline: str | None,
    caption_style: str,
    ai_headlines_enabled: bool,
) -> str:
    """Resolve display headline for publish based on runtime + stored style."""
    if not ai_headlines_enabled or caption_style == CAPTION_ORIGINAL:
        return original_title
    optimized = (optimized_headline or "").strip()
    if caption_style in (CAPTION_OPTIMIZED, CAPTION_HYBRID) and optimized:
        return optimized
    return original_title


def resolve_publish_hook(
    hook_line: str | None,
    *,
    ai_headlines_enabled: bool,
    caption_style: str,
) -> str | None:
    if not ai_headlines_enabled or caption_style == CAPTION_ORIGINAL:
        return None
    hook = (hook_line or "").strip()
    return hook or None
