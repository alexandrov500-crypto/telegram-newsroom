"""Extract explainable editorial features from draft/post content."""

from __future__ import annotations

import json
import re
from typing import Any

from publisher.public_renderer import split_headline_and_body

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]", re.UNICODE)
_URL_RE = re.compile(r"https?://[^\s<>]+|t\.me/[^\s<>]+", re.I)
_NUMBER_RE = re.compile(r"\d+[\d\s.,]*\d*|\d+")
_PERCENT_RE = re.compile(r"\d+\s*[%％]")
_CURRENCY_RE = re.compile(r"[$€£₽]|(?:руб|usd|eur|₽)\b", re.I)
_QUESTION_RE = re.compile(r"\?")
_QUOTE_RE = re.compile(r"[«»\"\"''„]")
_BULLET_LINE_RE = re.compile(r"^\s*(?:[•\-–—*]|\d+[.)])\s+", re.M)


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _source_count(sources: str | list[Any] | None) -> int:
    if isinstance(sources, list):
        return len(sources)
    try:
        parsed = json.loads(sources or "[]")
        return len(parsed) if isinstance(parsed, list) else 0
    except (json.JSONDecodeError, TypeError):
        return 0


def _headline_from_post(post: dict[str, Any]) -> str:
    title = str(post.get("editor_title") or post.get("headline") or "").strip()
    if title:
        return title
    content = str(post.get("content") or post.get("body") or "")
    headline, _ = split_headline_and_body(content)
    return headline


def _body_from_post(post: dict[str, Any]) -> str:
    summary = str(post.get("editor_summary") or post.get("body") or "").strip()
    if summary:
        return summary
    content = str(post.get("content") or "")
    _, body = split_headline_and_body(content)
    return body or content


def _uppercase_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for c in letters if c.isupper())
    return round(upper / len(letters), 4)


def extract_editorial_features(post: dict[str, Any]) -> dict[str, Any]:
    """Extract headline, body, and growth metadata features from a post/draft dict."""
    headline = _headline_from_post(post)
    body = _body_from_post(post)
    extras = post.get("draft_extras")
    if isinstance(extras, str):
        extras = _parse_json(extras)
    elif not isinstance(extras, dict):
        extras = {}

    growth = extras.get("growth") if isinstance(extras.get("growth"), dict) else {}
    format_profile = str(
        post.get("format_profile")
        or growth.get("format_profile")
        or extras.get("format_profile")
        or "cb_brief"
    )
    content_segment = str(post.get("content_segment") or extras.get("content_segment") or "general_news")
    virality_tier = str(
        post.get("virality_tier")
        or growth.get("virality_tier")
        or extras.get("virality_tier")
        or "standard"
    )

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body.strip()) if p.strip()] if body.strip() else []
    if not paragraphs and body.strip():
        paragraphs = [ln.strip() for ln in body.splitlines() if ln.strip()]

    features: dict[str, Any] = {
        "headline_length": len(headline),
        "headline_word_count": len(headline.split()) if headline else 0,
        "has_number": bool(_NUMBER_RE.search(headline)),
        "has_percent": bool(_PERCENT_RE.search(headline)),
        "has_currency": bool(_CURRENCY_RE.search(headline)),
        "has_question": bool(_QUESTION_RE.search(headline)),
        "has_colon": ":" in headline,
        "has_quote": bool(_QUOTE_RE.search(headline)),
        "uppercase_ratio": _uppercase_ratio(headline),
        "body_length": len(body),
        "paragraph_count": len(paragraphs),
        "bullet_count": len(_BULLET_LINE_RE.findall(body)),
        "emoji_count": len(_EMOJI_RE.findall(headline + "\n" + body)),
        "link_count": len(_URL_RE.findall(body)),
        "source_count": _source_count(post.get("sources")),
        "content_segment": content_segment,
        "format_profile": format_profile,
        "virality_tier": virality_tier,
    }
    return features


def draft_to_post_dict(
    *,
    draft_id: int,
    content: str,
    sources: str = "[]",
    draft_extras: str | None = None,
    editor_title: str | None = None,
    editor_summary: str | None = None,
    content_segment: str = "",
    format_profile: str = "",
    virality_tier: str = "",
) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "content": content,
        "sources": sources,
        "draft_extras": draft_extras or "{}",
        "editor_title": editor_title,
        "editor_summary": editor_summary,
        "content_segment": content_segment,
        "format_profile": format_profile,
        "virality_tier": virality_tier,
    }
