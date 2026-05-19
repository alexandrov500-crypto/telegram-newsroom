from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from openai import AsyncOpenAI

from bot.config import bootstrap_env, get_openai_api_key, get_openai_model

logger = logging.getLogger(__name__)

_LLM_TIMEOUT_SEC = 20.0
_MAX_TOKENS = 280
_TEMPERATURE = 0.2
_MAX_ATTEMPTS = 2
_MIN_TAGS = 2
_MAX_TAGS = 5
_MAX_SUMMARY_CHARS = 420

_TAG_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F600-\U0001F64F"
    "]+",
    flags=re.UNICODE,
)
_MARKDOWN_RE = re.compile(r"[*_`#>\[\]]+")

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "has",
        "have",
        "will",
        "into",
        "about",
        "after",
        "before",
        "over",
        "under",
        "news",
    }
)

_SYSTEM_PROMPT = (
    "You are a professional newsroom editor. "
    "Produce factual, concise copy with no hype, no emojis, and no markdown."
)

_USER_PROMPT_TEMPLATE = """Summarize this RSS item for a Telegram news channel.

Title: {title}
Source: {source}
Link: {link}

Rules:
- summary: 1–2 concise factual sentences (newsroom tone, no hype, no emojis)
- tags: 2–5 short lowercase single-word or hyphenated tokens (no # prefix)
- confidence: float 0.0–1.0 for how well the summary reflects the title/link context
- title: cleaned headline (plain text, no emojis)

Return STRICT JSON only:
{{
  "title": "...",
  "summary": "...",
  "tags": ["...", "..."],
  "confidence": 0.0
}}"""

_MEMORY_CONTEXT_TEMPLATE = """

Ongoing story context (maintain continuity; avoid repeating prior facts verbatim):
{memory_block}
"""


def _extract_tags(title: str, *, limit: int = 3) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for match in _TAG_WORD.findall(title):
        token = match.lower()
        if token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        tags.append(token)
        if len(tags) >= limit:
            break
    return tags


def _sanitize_text(value: str, *, max_len: int | None = None) -> str:
    text = _MARKDOWN_RE.sub("", value)
    text = _EMOJI_RE.sub("", text)
    text = " ".join(text.split())
    if max_len is not None and len(text) > max_len:
        cut = text[:max_len].rsplit(" ", 1)[0]
        text = cut.rstrip(".,;:") + "…" if cut else text[:max_len]
    return text.strip()


def _normalize_tags(raw_tags: Any, *, title: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            token = str(tag).strip().lstrip("#").lower().replace(" ", "_")
            token = re.sub(r"[^a-z0-9\-_]", "", token)
            if not token or token in seen:
                continue
            seen.add(token)
            tags.append(token)
            if len(tags) >= _MAX_TAGS:
                break
    if len(tags) < _MIN_TAGS:
        for fallback in _extract_tags(title, limit=_MAX_TAGS):
            if fallback not in seen:
                seen.add(fallback)
                tags.append(fallback)
            if len(tags) >= _MIN_TAGS:
                break
    return tags[:_MAX_TAGS]


def _parse_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def _parse_llm_payload(content: str, *, fallback_title: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a JSON object")

    title = _sanitize_text(str(data.get("title") or fallback_title))
    summary = _sanitize_text(str(data.get("summary", "")), max_len=_MAX_SUMMARY_CHARS)
    if not summary:
        raise ValueError("LLM summary is empty")

    tags = _normalize_tags(data.get("tags"), title=title or fallback_title)
    confidence = _parse_confidence(data.get("confidence"))

    return {
        "title": title or fallback_title,
        "summary": summary,
        "tags": tags,
        "confidence": confidence,
    }


async def _placeholder_summarize(title: str, link: str, source: str) -> dict:
    _ = link, source
    summary = _sanitize_text(f"Short summary: {title}", max_len=_MAX_SUMMARY_CHARS)
    tags = _extract_tags(title, limit=_MAX_TAGS)
    if len(tags) < _MIN_TAGS:
        tags = (tags + ["news"])[:_MAX_TAGS]

    return {
        "title": _sanitize_text(title),
        "summary": summary,
        "tags": tags,
        "confidence": 0.0,
    }


def _token_estimate(response: Any) -> int | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    return int(total) if total is not None else None


def _is_retryable(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "timeout" in name or "connection" in name:
        return True
    message = str(exc).lower()
    return "rate limit" in message or "timeout" in message or "503" in message


def _build_user_prompt(
    *,
    title: str,
    link: str,
    source: str,
    story_context: dict[str, str] | None,
) -> str:
    prompt = _USER_PROMPT_TEMPLATE.format(title=title, source=source, link=link)
    if not story_context:
        return prompt
    timeline = story_context.get("timeline", "").strip()
    summary = story_context.get("canonical_summary", "").strip()
    prior_title = story_context.get("title", "").strip()
    parts: list[str] = []
    if prior_title:
        parts.append(f"Story headline: {prior_title}")
    if summary:
        parts.append(f"Latest summary: {summary}")
    if timeline:
        parts.append(timeline)
    if not parts:
        return prompt
    memory_block = "\n".join(parts)
    return prompt + _MEMORY_CONTEXT_TEMPLATE.format(memory_block=memory_block)


async def _call_openai_chat(
    *,
    client: AsyncOpenAI,
    model: str,
    title: str,
    link: str,
    source: str,
    story_context: dict[str, str] | None = None,
) -> tuple[str, Any]:
    user_prompt = _build_user_prompt(
        title=title,
        link=link,
        source=source,
        story_context=story_context,
    )

    async def _request() -> Any:
        return await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )

    response = await asyncio.wait_for(_request(), timeout=_LLM_TIMEOUT_SEC)
    content = response.choices[0].message.content
    if not content:
        raise ValueError("empty LLM response content")
    return content, response


async def _llm_summarize(
    title: str,
    link: str,
    source: str,
    *,
    api_key: str,
    model: str,
    story_context: dict[str, str] | None = None,
) -> dict:
    client = AsyncOpenAI(
        api_key=api_key,
        timeout=_LLM_TIMEOUT_SEC,
        max_retries=0,
    )
    started = time.perf_counter()
    last_error: BaseException | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            content, response = await _call_openai_chat(
                client=client,
                model=model,
                title=title,
                link=link,
                source=source,
                story_context=story_context,
            )
            try:
                result = _parse_llm_payload(content, fallback_title=title)
            except (json.JSONDecodeError, ValueError) as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.warning(
                    "event=llm_response_invalid model=%r duration_ms=%d error=%r attempt=%d",
                    model,
                    duration_ms,
                    exc,
                    attempt + 1,
                )
                last_error = exc
                if attempt + 1 < _MAX_ATTEMPTS:
                    continue
                raise

            duration_ms = int((time.perf_counter() - started) * 1000)
            token_estimate = _token_estimate(response)
            usage = getattr(response, "usage", None)
            if usage is not None:
                from bot.observability.metrics import record_openai_usage

                record_openai_usage(
                    operation="summarization",
                    model=model,
                    prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    success=True,
                )
            logger.info(
                "event=llm_summary_success model=%r duration_ms=%d token_estimate=%s "
                "tags=%r confidence=%s",
                model,
                duration_ms,
                token_estimate,
                result["tags"],
                result["confidence"],
            )
            return result
        except asyncio.TimeoutError as exc:
            last_error = exc
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "event=llm_summary_failed model=%r duration_ms=%d reason=timeout attempt=%d",
                model,
                duration_ms,
                attempt + 1,
            )
            if attempt + 1 < _MAX_ATTEMPTS:
                continue
            raise
        except Exception as exc:
            last_error = exc
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "event=llm_summary_failed model=%r duration_ms=%d error=%r attempt=%d",
                model,
                duration_ms,
                exc,
                attempt + 1,
            )
            if attempt + 1 < _MAX_ATTEMPTS and _is_retryable(exc):
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM summarize exhausted attempts")


def _fallback_reason(exc: BaseException | None, *, missing_key: bool) -> str:
    if missing_key:
        return "missing_openai_api_key"
    if exc is None:
        return "unknown"
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, ValueError):
        return "invalid_response"
    name = type(exc).__name__.lower()
    if "ratelimit" in name:
        return "rate_limit"
    return "llm_error"


async def summarize_news(
    title: str,
    link: str,
    source: str,
    *,
    story_context: dict[str, str] | None = None,
) -> dict:
    """
    Enrich a news item with LLM summary/tags, falling back to deterministic rules.

    Returns {"title", "summary", "tags", "confidence"}.
    Never raises — safe for ingestion loops.
    """
    bootstrap_env()
    api_key = get_openai_api_key()
    model = get_openai_model()

    if not api_key:
        logger.info("event=llm_fallback_used reason=missing_openai_api_key")
        return await _placeholder_summarize(title, link, source)

    error: BaseException | None = None
    try:
        return await _llm_summarize(
            title,
            link,
            source,
            api_key=api_key,
            model=model,
            story_context=story_context,
        )
    except Exception as exc:
        error = exc

    from bot.observability.metrics import record_summarization_failure

    record_summarization_failure()
    reason = _fallback_reason(error, missing_key=False)
    logger.info("event=llm_fallback_used reason=%s", reason)
    return await _placeholder_summarize(title, link, source)
