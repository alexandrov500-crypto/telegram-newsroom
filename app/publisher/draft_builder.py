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
_COLON_DASH_ATTRIB = re.compile(r":\s*[-–—]\s*")
_BROKEN_QUOTE_TAIL = re.compile(
    r",?\s*(?:что\s+)?(?:все,\s*)?что\s+[^.!?]{0,200}\b\w+(?:ского|ского|ного|ной|ному|ными)\.?\s*$",
    re.I,
)
_ATTRIB_AFTER_THOUGHT = re.compile(r"\.\s*(?:[Сс]казал|[Зз]аявил|[Пp]о\s+словам|[дД]обавил)\b")


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
    raw = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
    text = strip_telegram_markdown(str(raw or fallback_text))
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


def _normalize_colon_attribution(text: str) -> str:
    """«отношений: - Сказал Пашиняну» → «отношений. Сказал Пашиняну»."""
    t = (text or "").strip()
    t = _COLON_DASH_ATTRIB.sub(". ", t)
    return re.sub(r"\s+", " ", t).strip()


def _strip_broken_quote_tail(text: str, *, had_ellipsis: bool) -> str:
    """Drop a clause that was cut mid-phrase after the model/source ellipsis."""
    t = (text or "").rstrip()
    if not t:
        return t
    if had_ellipsis and _ATTRIB_AFTER_THOUGHT.search(t):
        t = t[: _ATTRIB_AFTER_THOUGHT.search(t).start()].rstrip()
    if had_ellipsis or _BROKEN_QUOTE_TAIL.search(t):
        trimmed = _BROKEN_QUOTE_TAIL.sub("", t).rstrip()
        if trimmed and len(trimmed) >= 40:
            t = trimmed
    # Orphan name stub after a bad cut («… Пашиняну.»).
    t = re.sub(r"[.:]\s*[А-ЯЁA-Z][а-яё]{2,20}\.\s*$", ".", t).rstrip()
    return t


def polish_channel_post(body: str, *, max_chars: int = 2800) -> str:
    """Reader-facing post: no sources, full sentences, no lazy trailing ellipsis."""
    clean = strip_source_attribution(normalize_legacy_bullet_lines(body))
    clean = strip_telegram_markdown(clean)
    clean = _normalize_colon_attribution(clean)
    if not clean:
        return "News update."
    had_ellipsis = bool(_TRAIL_ELLIPSIS.search(clean))
    if had_ellipsis:
        clean = _TRAIL_ELLIPSIS.sub("", clean).rstrip()
        clean = _strip_broken_quote_tail(clean, had_ellipsis=True)
    elif not clean.rstrip().endswith((".", "!", "?", "…")):
        clean = complete_story_text(clean, max_chars=max_chars)
    if len(clean) > max_chars:
        clean = complete_story_text(clean, max_chars=max_chars)
    from app.editorial.content_quality import is_truncated_mid_thought

    if not is_truncated_mid_thought(clean):
        clean = _finish_thought(clean)
    elif had_ellipsis:
        # Prefer dropping to the last complete sentence rather than faking an ending.
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", clean) if p.strip()]
        if len(parts) > 1:
            clean = " ".join(parts[:-1]).strip()
            clean = _finish_thought(clean)
    clean = clean.strip()
    if os.getenv("HEADLINE_ENGINE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from app.editorial.headline_engine import apply_headline_to_content, pick_best_headline

            headline = pick_best_headline(clean, vertical="macro")
            clean = apply_headline_to_content(clean, headline)
        except Exception:
            pass
    return clean


def _finish_thought(text: str) -> str:
    """Remove a dangling clause opener and ensure a terminal sentence mark.

    A body ending in «… компании нет:» or «… потому что,» is a cut-off
    thought. Drop the trailing connector/colon and, if the remaining text is a
    complete clause, close it with a period so it reads as a finished sentence.
    """
    t = (text or "").rstrip()
    if not t:
        return t
    t = re.sub(r"(\.\.\.|…)$", "", t).rstrip()
    # Trailing colon / dash / conjunction signals an unfinished continuation.
    t = re.sub(
        r"[\s,;:–—-]*\b(и|или|а|но|потому что|поскольку|так как|что|чтобы)\s*$",
        "",
        t,
        flags=re.I,
    ).rstrip()
    t = re.sub(r"[\s,;:–—-]+$", "", t).rstrip()
    if t and t[-1] not in ".!?…":
        t = f"{t}."
    return t


# YandexGPT / relay models sometimes drop the first letter of a proper name at sentence start.
_LEADING_NAME_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^утин\b", re.I), "Путин"),
    (re.compile(r"^утина\b", re.I), "Путина"),
    (re.compile(r"^утине\b", re.I), "Путине"),
)


def _repair_leading_name_glitches(text: str) -> str:
    if not (text or "").strip():
        return text or ""
    lines = (text or "").splitlines()
    if not lines:
        return text
    first = lines[0]
    for pat, repl in _LEADING_NAME_FIXES:
        first = pat.sub(repl, first, count=1)
    if first != lines[0]:
        lines[0] = first
        return "\n".join(lines)
    return text


def finalize_draft_content(body: str, *, max_chars: int = 2800) -> str:
    """Last-mile cleanup before DB / admin notify (strip markdown, complete sentences)."""
    return polish_channel_post(_repair_leading_name_glitches(body), max_chars=max_chars)


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
