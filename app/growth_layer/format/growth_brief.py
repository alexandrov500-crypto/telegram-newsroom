"""Newsroom360 Growth Brief — four-block publish format."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from publisher.public_renderer import clean_headline
from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

GROWTH_HEADLINE_MAX = 120
GROWTH_BODY_MAX_CHARS = 960

_BLOCK_LABELS = (
    ("what_happened", "⚡ Что произошло"),
    ("why_important", "📊 Почему это важно"),
    ("money_impact", "💰 Что это значит для денег"),
    ("what_next", "🎯 Что будет дальше"),
)


@dataclass(frozen=True)
class GrowthBriefBlocks:
    headline: str
    what_happened: str
    why_important: str
    money_impact: str
    what_next: str

    def to_dict(self) -> dict[str, str]:
        return {
            "headline": self.headline,
            "what_happened": self.what_happened,
            "why_important": self.why_important,
            "money_impact": self.money_impact,
            "what_next": self.what_next,
        }


def _finish(s: str) -> str:
    t = (s or "").strip().rstrip("…")
    if not t:
        return t
    if t[-1] not in ".!?":
        return f"{t}."
    return t


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split((text or "").strip()) if len(s.strip()) > 10]


def blocks_from_llm_json(data: dict[str, Any], *, headline_fallback: str = "") -> GrowthBriefBlocks:
    headline = clean_headline(str(data.get("headline") or headline_fallback or ""), max_len=GROWTH_HEADLINE_MAX)
    return GrowthBriefBlocks(
        headline=headline,
        what_happened=_finish(str(data.get("what_happened") or data.get("post") or "")),
        why_important=_finish(str(data.get("why_important") or "")),
        money_impact=_finish(str(data.get("money_impact") or "")),
        what_next=_finish(str(data.get("what_next") or "")),
    )


def blocks_from_plain_text(headline: str, body: str) -> GrowthBriefBlocks:
    h = clean_headline((headline or "").strip(), max_len=GROWTH_HEADLINE_MAX)
    sents = _sentences(body)
    if not h and sents:
        h = clean_headline(sents[0], max_len=GROWTH_HEADLINE_MAX)
        sents = sents[1:]
    if not sents:
        sents = _sentences(body) or [body.strip()[:240]]

    n = len(sents)
    if n == 1:
        groups = [sents[0], sents[0], sents[0], sents[0]]
    elif n == 2:
        groups = [sents[0], sents[1], sents[1], sents[1]]
    elif n == 3:
        groups = [sents[0], sents[1], sents[2], sents[2]]
    elif n == 4:
        groups = sents
    else:
        groups = [
            " ".join(sents[: max(1, n // 4)]),
            " ".join(sents[max(1, n // 4) : max(2, n // 2)]),
            " ".join(sents[max(2, n // 2) : max(3, n - 1)]),
            sents[-1],
        ]

    return GrowthBriefBlocks(
        headline=h,
        what_happened=_finish(groups[0]),
        why_important=_finish(groups[1]),
        money_impact=_finish(groups[2]),
        what_next=_finish(groups[3]),
    )


def resolve_growth_blocks(
    *,
    headline: str,
    body: str,
    growth_meta: dict[str, Any] | None = None,
) -> GrowthBriefBlocks:
    if growth_meta:
        raw_blocks = growth_meta.get("brief_blocks")
        if isinstance(raw_blocks, dict):
            merged = dict(raw_blocks)
            if headline and not merged.get("headline"):
                merged["headline"] = headline
            return blocks_from_llm_json(merged, headline_fallback=headline)
    return blocks_from_plain_text(headline, body)


def compose_growth_brief_body(blocks: GrowthBriefBlocks, *, max_chars: int = GROWTH_BODY_MAX_CHARS) -> str:
    parts: list[str] = []
    for key, label in _BLOCK_LABELS:
        text = _finish(getattr(blocks, key))
        if text:
            parts.append(f"{label}\n{text}")
    out = "\n\n".join(parts).strip()
    if len(out) > max_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_chars)
    return out


def compose_growth_brief(blocks: GrowthBriefBlocks, *, max_chars: int = GROWTH_BODY_MAX_CHARS + GROWTH_HEADLINE_MAX) -> str:
    parts: list[str] = []
    if blocks.headline:
        parts.append(blocks.headline)
        parts.append("")
    for key, label in _BLOCK_LABELS:
        text = _finish(getattr(blocks, key))
        if text:
            parts.append(f"{label}\n{text}")
    out = "\n\n".join(parts).strip()
    if len(out) > max_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_chars)
    return out


def render_growth_brief_html(blocks: GrowthBriefBlocks) -> str:
    parts: list[str] = []
    if blocks.headline:
        parts.append(f"<b>{escape_telegram_html(blocks.headline)}</b>")
    for key, label in _BLOCK_LABELS:
        text = _finish(getattr(blocks, key))
        if not text:
            continue
        parts.append(f"<b>{escape_telegram_html(label)}</b>\n{escape_telegram_html(text)}")
    return sanitize_telegram_html_output("\n\n".join(parts))
