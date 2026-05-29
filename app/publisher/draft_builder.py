"""Draft body builder — breaking minimal vs hierarchical compressed digest."""

from __future__ import annotations

import os
import re
from typing import Any

from app.editorial.compression import CompressedCluster
from app.editorial.story_types import StoryType

_WS = re.compile(r"\s+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_MD_UNDER = re.compile(r"__([^_]+)__")
_LEAD_CHANNEL = re.compile(r"^(?:\[@\w+\]|@\w+)\s*")
_INLINE_CHANNEL = re.compile(r"(?:\[@?[\w]{3,64}\]|@\w{3,64})")
_SOURCES_LINE = re.compile(r"^(?:источники|sources)\s*:", re.IGNORECASE)
_TRAIL_ELLIPSIS = re.compile(r"(?<=\w)(?:\.{3,}|…)\s*$")


def _one_line_max() -> int:
    try:
        return max(120, int(os.getenv("EDITORIAL_ONE_LINE_MAX", "480")))
    except ValueError:
        return 480


def strip_telegram_markdown(text: str) -> str:
    """Plain text for drafts: links → label, drop ** / *, trim leading @channel tag."""
    t = (text or "").strip()
    t = _MD_LINK.sub(r"\1", t)
    t = _MD_BOLD.sub(r"\1", t)
    t = _MD_ITALIC.sub(r"\1", t)
    t = _MD_UNDER.sub(r"\1", t)
    t = _LEAD_CHANNEL.sub("", t)
    return _WS.sub(" ", t).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 20]


def complete_story_text(text: str, *, max_chars: int = 2800) -> str:
    """Prefer full sentences; only truncate when over max_chars."""
    clean = strip_telegram_markdown(text)
    if not clean:
        return ""
    if len(clean) <= max_chars:
        return clean
    sents = _sentences(clean)
    if not sents:
        return _truncate_at_sentence(clean, max_chars)
    parts = [sents[0]]
    for s in sents[1:]:
        candidate = " ".join(parts + [s])
        if len(candidate) > max_chars:
            break
        parts.append(s)
    joined = " ".join(parts)
    if len(joined) >= len(clean):
        return joined
    if len(parts) == 1 and len(parts[0]) > max_chars:
        return _truncate_at_sentence(parts[0], max_chars)
    return joined.rstrip()


def _truncate_at_sentence(text: str, max_len: int) -> str:
    """Trim only at sentence/word boundaries — no trailing ellipsis."""
    if len(text) <= max_len:
        return text
    chunk = text[:max_len]
    for sep in (". ", "! ", "? ", " — ", "; "):
        pos = chunk.rfind(sep)
        if pos > max_len // 2:
            return chunk[: pos + len(sep.rstrip())].rstrip()
    sp = chunk.rfind(" ")
    if sp > max_len // 3:
        return chunk[:sp].rstrip()
    return chunk.rstrip()


def _one_line_summary(text: str, *, max_len: int | None = None) -> str:
    limit = max_len if max_len is not None else _one_line_max()
    clean = strip_telegram_markdown(text)
    if not clean:
        return ""
    sents = _sentences(clean)
    if not sents:
        return _truncate_at_sentence(clean, limit)
    if len(sents) == 1:
        return _truncate_at_sentence(sents[0], limit)
    combined = sents[0]
    for s in sents[1:]:
        if len(combined) + 2 + len(s) > limit:
            break
        combined = f"{combined} {s}"
    return _truncate_at_sentence(combined, limit)


def format_single_source_draft(
    item: dict[str, Any],
    *,
    max_chars: int = 2800,
    fallback_text: str = "",
) -> str:
    """One Telegram post → readable blurb (no channel tag, no raw markdown)."""
    text = strip_telegram_markdown(str(item.get("text") or fallback_text))
    if not text:
        return "News update."
    summary = complete_story_text(text, max_chars=max_chars)
    return polish_channel_post(summary, max_chars=max_chars)


def render_hierarchical_draft(clusters: list[CompressedCluster]) -> str:
    """
    Hierarchical format (no flat list):
    BREAKING → TOP STORIES → OTHER IMPORTANT
    """
    if not clusters:
        return "No stories passed editorial compression."

    if len(clusters) == 1 and len(clusters[0].items) == 1:
        return format_single_source_draft(clusters[0].items[0])

    sections: list[str] = []
    breaking_done = False
    top_done = False

    for c in clusters:
        if not c.items:
            continue
        st = c.story_type
        if st == StoryType.BREAKING.value and not breaking_done:
            title = "⚡ BREAKING"
            breaking_done = True
            max_items = 1
        elif not top_done:
            title = "📌 TOP STORIES"
            top_done = True
            max_items = 2
        else:
            title = "📋 OTHER IMPORTANT"
            max_items = 2

        lines = [title]
        for it in c.items[:max_items]:
            summary = _one_line_summary(str(it.get("text") or ""))
            if not summary:
                continue
            lines.append(f"• {summary}")
        if len(lines) > 1:
            sections.append("\n".join(lines))

    if not sections:
        return "No stories passed editorial compression."
    return "\n\n".join(sections)


def normalize_legacy_bullet_lines(body: str) -> str:
    """Turn «• [@channel] …» bullets into plain paragraphs (no channel tags)."""
    paragraphs: list[str] = []
    pending: list[str] = []
    for line in (body or "").splitlines():
        s = line.strip()
        if not s:
            if pending:
                paragraphs.append(" ".join(pending))
                pending = []
            continue
        if s.startswith("•"):
            bullet = re.sub(r"^•\s*(?:\[@?\w+\]\s*)+", "", s).strip()
            bullet = strip_telegram_markdown(bullet)
            if bullet:
                pending.append(bullet)
            continue
        if pending:
            paragraphs.append(" ".join(pending))
            pending = []
        paragraphs.append(strip_telegram_markdown(s))
    if pending:
        paragraphs.append(" ".join(pending))
    return "\n\n".join(p for p in paragraphs if p).strip()


def strip_source_attribution(text: str) -> str:
    """Remove channel handles and «Sources / Источники» lines from reader-facing text."""
    lines: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if _SOURCES_LINE.match(s):
            continue
        s = _INLINE_CHANNEL.sub("", s)
        s = _LEAD_CHANNEL.sub("", s)
        s = _WS.sub(" ", s).strip()
        if s:
            lines.append(s)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def polish_channel_post(body: str, *, max_chars: int = 2800) -> str:
    """Reader-facing post: no sources, full sentences, no lazy trailing ellipsis."""
    clean = strip_source_attribution(normalize_legacy_bullet_lines(body))
    clean = strip_telegram_markdown(clean)
    if not clean:
        return "News update."
    if _TRAIL_ELLIPSIS.search(clean):
        clean = _TRAIL_ELLIPSIS.sub("", clean).rstrip()
        clean = complete_story_text(clean, max_chars=max_chars)
    elif not clean.rstrip().endswith((".", "!", "?", "…")):
        clean = complete_story_text(clean, max_chars=max_chars)
    if len(clean) > max_chars:
        clean = complete_story_text(clean, max_chars=max_chars)
    return clean.strip()


def finalize_draft_content(body: str, *, max_chars: int = 2800) -> str:
    """Last-mile cleanup before DB / admin notify (strip markdown, complete sentences)."""
    return polish_channel_post(body, max_chars=max_chars)


def build_draft_body(
    text: str,
    *,
    breaking: bool = False,
    sources: list[dict[str, Any]] | None = None,
    max_chars: int = 2800,
) -> str:
    """
    BREAKING: 1–2 bullets, no aggregation.
    NORMAL: pass-through trim (use build_compressed_draft_from_posts for hierarchy).
    """
    clean = strip_telegram_markdown(text)
    if not clean:
        return "News update."

    if breaking:
        sents = _sentences(clean)
        bullets: list[str] = []
        if sents:
            bullets.append(f"• {_truncate_at_sentence(sents[0], 500)}")
        if len(sents) > 1 and len(bullets) < 2:
            bullets.append(f"• {_truncate_at_sentence(sents[1], 500)}")
        if not bullets:
            bullets.append(f"• {_truncate_at_sentence(clean, 500)}")
        body = "\n".join(bullets[:2])
        return polish_channel_post(body, max_chars=max_chars)

    if len(clean) > max_chars:
        return complete_story_text(clean, max_chars=max_chars)
    return clean
