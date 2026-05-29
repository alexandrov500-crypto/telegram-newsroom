"""Public channel vs internal moderation rendering (strict separation)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.publisher.draft_builder import polish_channel_post, strip_telegram_markdown
from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output

# Section headers / labels that must never appear on the public channel.
_INTERNAL_SECTION_RE = re.compile(
    r"^(\s*)(Quality|Duplicates|Priority|Category confidence|Source reputation|"
    r"Title suggestions|Cluster|Governance|Editorial scores|Publish warnings|"
    r"Draft ID|Sources \(JSON\)|Источники \(JSON\)|"
    r"Качество|Дубликаты|Приоритет|Уверенность в категории|Репутация источников|"
    r"Варианты заголовка|Редакционная оценка|Предупреждения к публикации|"
    r"ID черновика)\b",
    re.IGNORECASE,
)
_DIGEST_HEADER_RE = re.compile(r"^[⚡📌📋🔥]\s*(BREAKING|TOP STORIES|OTHER IMPORTANT|Срочно|Главное).*$", re.I)
_METRIC_LINE_RE = re.compile(
    r"^\s*[\w.]+\s*:\s*(0\.\d+|\d+%|high|medium|low|высок|средн|низк)\s*$",
    re.I,
)
_URL_RAW_RE = re.compile(r"https?://\S+")
_DUP_CHANNEL_PREFIX_RE = re.compile(r"^(?:\[@?[\w]{2,64}\]\s*)+", re.MULTILINE)
_WHY_IT_MATTERS_RE = re.compile(
    r"^(Почему это важно|Why it matters)\s*:?\s*",
    re.I,
)


def _public_headline_max() -> int:
    try:
        return max(40, min(200, int(os.getenv("PUBLIC_HEADLINE_MAX_CHARS", "140"))))
    except ValueError:
        return 140


def _public_body_max() -> int:
    try:
        default = os.getenv("MAX_POST_CHARS", "3500")
        return max(400, int(os.getenv("PUBLIC_BODY_MAX_CHARS", default)))
    except ValueError:
        return 3500


def _why_it_matters_enabled() -> bool:
    return os.getenv("PUBLIC_WHY_IT_MATTERS", "true").strip().lower() in {"1", "true", "yes", "on"}


def extract_why_it_matters(text: str) -> tuple[str, str]:
    """Split optional 'why it matters' block from body (plain text)."""
    lines = (text or "").splitlines()
    body_lines: list[str] = []
    why_lines: list[str] = []
    in_why = False
    for line in lines:
        s = line.strip()
        if _WHY_IT_MATTERS_RE.match(s):
            in_why = True
            rest = _WHY_IT_MATTERS_RE.sub("", s).strip()
            if rest:
                why_lines.append(rest)
            continue
        if in_why:
            if not s:
                if why_lines:
                    break
                continue
            if _INTERNAL_SECTION_RE.match(s):
                body_lines.append(line)
                in_why = False
                continue
            why_lines.append(s)
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    why = " ".join(why_lines).strip()
    if len(why) > 480:
        why = why[:477].rstrip() + "…"
    return body, why


def format_why_it_matters_block(why: str) -> str:
    w = (why or "").strip()
    if not w:
        return ""
    return f"Почему это важно:\n{w}"


def _source_footer_style() -> str:
    raw = os.getenv("PUBLIC_SOURCE_ATTRIBUTION_STYLE", "source").strip().lower()
    return "via" if raw == "via" else "source"


def strip_internal_debug_text(text: str) -> str:
    """Remove moderation/diagnostic blocks accidentally present in draft body."""
    lines = (text or "").splitlines()
    out: list[str] = []
    skip_block = False
    for line in lines:
        s = line.strip()
        if not s:
            if not skip_block:
                out.append("")
            continue
        if _INTERNAL_SECTION_RE.match(s) or _DIGEST_HEADER_RE.match(s):
            skip_block = True
            continue
        if skip_block and (s.startswith("•") or _METRIC_LINE_RE.match(s)):
            continue
        if _INTERNAL_SECTION_RE.match(s):
            skip_block = True
            continue
        skip_block = False
        if _METRIC_LINE_RE.match(s):
            continue
        out.append(line)
    joined = "\n".join(out)
    joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
    return joined


def clean_headline(text: str, *, max_len: int | None = None) -> str:
    limit = max_len if max_len is not None else _public_headline_max()
    t = strip_telegram_markdown(text or "")
    t = _DUP_CHANNEL_PREFIX_RE.sub("", t).strip()
    t = _URL_RAW_RE.sub("", t).strip()
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= limit:
        return t
    cut = t[: limit + 1]
    sp = cut.rfind(" ")
    if sp > limit // 2:
        return cut[:sp].rstrip()
    return t[:limit].rstrip()


def split_headline_and_body(clean_text: str) -> tuple[str, str]:
    """Derive headline + body from polished plain text."""
    t = (clean_text or "").strip()
    if not t:
        return "", ""
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    filtered: list[str] = []
    for ln in lines:
        if _DIGEST_HEADER_RE.match(ln):
            continue
        if ln.startswith("•"):
            filtered.append(ln.lstrip("•").strip())
        else:
            filtered.append(ln)
    if not filtered:
        return "", ""
    if len(filtered) == 1:
        blob = filtered[0]
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", blob) if x.strip()]
        if len(sents) >= 2 and len(sents[0]) <= _public_headline_max():
            body = " ".join(sents[1:])[:_public_body_max()].strip()
            return clean_headline(sents[0]), body
        # Single-sentence / teaser line: keep substance in body, short headline from lead.
        from app.editorial.public_post_template import normalize_lead_emoji

        blob = normalize_lead_emoji(blob)
        # «Спикер: тезис» — headline only before the colon; never split mid-sentence by word count.
        if ":" in blob:
            head, _, tail = blob.partition(":")
            head, tail = head.strip(), tail.strip()
            if head and tail and len(head) <= _public_headline_max() and len(tail) >= 24:
                return clean_headline(head), tail
        return "", blob
    headline = clean_headline(filtered[0])
    body = "\n\n".join(filtered[1:]).strip()
    return headline, body


def primary_source_handle(sources: str | list[dict[str, Any]] | None) -> str | None:
    """Single primary @channel (no message ids)."""
    rows: list[dict[str, Any]] = []
    if isinstance(sources, list):
        rows = [r for r in sources if isinstance(r, dict)]
    else:
        try:
            parsed = json.loads(sources or "[]")
            if isinstance(parsed, list):
                rows = [r for r in parsed if isinstance(r, dict)]
        except (json.JSONDecodeError, TypeError):
            return None
    if not rows:
        return None
    counts: dict[str, int] = {}
    for r in rows:
        ch = str(r.get("channel") or "").strip()
        if not ch:
            continue
        key = ch if ch.startswith("@") else f"@{ch.lstrip('@')}"
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return max(counts.keys(), key=lambda k: (counts[k], k))


def format_source_footer(handle: str, *, style: str | None = None) -> str:
    h = (handle or "").strip()
    if not h:
        return ""
    if not h.startswith("@"):
        h = f"@{h.lstrip('@')}"
    st = style or _source_footer_style()
    if st == "via":
        return f"via {h}"
    return f"Источник: {h}"


def _format_body_html(body: str) -> str:
    if not body:
        return ""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [body.strip()]
    return "\n\n".join(escape_telegram_html(p) for p in paragraphs)


def render_public_post(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    tags: list[str] | None = None,
    why_it_matters: str | None = None,
    max_total_chars: int = 12000,
) -> str:
    """Plain-text public post (headline, body, source footer)."""
    polished = polish_channel_post(
        strip_internal_debug_text(content),
        max_chars=_public_body_max(),
    )
    headline, body = split_headline_and_body(polished)
    body, embedded_why = extract_why_it_matters(body)
    why = (why_it_matters or embedded_why or "").strip()
    from app.editorial.public_format import format_public_story

    story = format_public_story(headline, body, why_it_matters=why)
    headline, body, why = story.headline, story.summary, story.why_it_matters
    parts: list[str] = []
    if headline:
        parts.append(headline)
    if body:
        parts.append(body)
    if _why_it_matters_enabled() and why:
        parts.append("")
        parts.append(format_why_it_matters_block(why))
    handle = primary_source_handle(sources)
    if handle:
        parts.append("")
        parts.append(format_source_footer(handle))
    if tags:
        tag_line = " ".join(t for t in tags if str(t).strip())[:120]
        if tag_line:
            parts.append("")
            parts.append(tag_line)
    out = "\n".join(parts).strip()
    if len(out) > max_total_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_total_chars)
    return out


def render_public_post_html(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    draft_id: int | None = None,
    tags: list[str] | None = None,
    why_it_matters: str | None = None,
    max_total_chars: int = 12000,
) -> str:
    """
    HTML for Telegram channel: headline, summary, optional tags, source footer only.
    ``draft_id`` is ignored (never rendered publicly).
    """
    _ = draft_id
    polished = polish_channel_post(
        strip_internal_debug_text(content),
        max_chars=_public_body_max(),
    )
    headline, body = split_headline_and_body(polished)
    body, embedded_why = extract_why_it_matters(body)
    why = (why_it_matters or embedded_why or "").strip()
    from app.editorial.public_format import format_public_story

    story = format_public_story(headline, body, why_it_matters=why)
    headline, body, why = story.headline, story.summary, story.why_it_matters
    parts: list[str] = []
    if headline:
        parts.append(f"<b>{escape_telegram_html(headline)}</b>")
    body_html = _format_body_html(body)
    if body_html:
        parts.append(body_html)
    if _why_it_matters_enabled() and why:
        parts.append(
            f"<i>{escape_telegram_html('Почему это важно:')}</i>\n{escape_telegram_html(why)}"
        )
    handle = primary_source_handle(sources)
    if handle:
        parts.append(f"<i>{escape_telegram_html(format_source_footer(handle))}</i>")
    if tags:
        tag_line = " ".join(escape_telegram_html(str(t)) for t in tags if str(t).strip())[:12]
        if tag_line:
            parts.append(f"<i>{tag_line}</i>")
    out = "\n\n".join(p for p in parts if p)
    if len(out) > max_total_chars:
        out = out[:max_total_chars].rstrip()
    return sanitize_telegram_html_output(out)


def render_internal_review_html(
    draft_id: int,
    content: str,
    sources: str | list[dict[str, Any]] | None,
    *,
    editor_title: str | None = None,
    editor_summary: str | None = None,
    draft_extras_json: str | None = None,
    status: str = "pending",
    created_at_iso: str = "",
    scheduled_at_iso: str | None = None,
    publish_warnings: list[str] | None = None,
    duplicate_intel: dict[str, Any] | None = None,
    editorial_intelligence: dict[str, Any] | None = None,
    max_chars: int = 3800,
) -> str:
    """Full moderation / diagnostics view (admin bot only)."""
    from publisher.formatting import render_rich_draft_preview_html

    html = render_rich_draft_preview_html(
        draft_id,
        content,
        sources,
        editor_title=editor_title,
        editor_summary=editor_summary,
        draft_extras_json=draft_extras_json,
        status=status,
        created_at_iso=created_at_iso,
        scheduled_at_iso=scheduled_at_iso,
        publish_warnings=publish_warnings,
        duplicate_intel=duplicate_intel,
        max_chars=max_chars,
    )
    if editorial_intelligence:
        from editorial.scoring.preview import render_editorial_intelligence_html

        block = render_editorial_intelligence_html(editorial_intelligence)
        if block:
            html = html + block
    return html
