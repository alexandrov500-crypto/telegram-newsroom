"""Single public post formatter — headline, summary, why-it-matters, attribution, CTA."""

from __future__ import annotations

import json
import re
from typing import Any

from app.editorial.public_format import format_public_story
from app.editorial.publish_body_scrubber import scrub_publish_plaintext
from app.editorial.source_attribution import (
    apply_attribution_to_footer,
    resolve_source_attribution,
    strip_raw_urls,
)
from app.editorial.tuning_loader import get_editorial_tuning
from app.publisher.draft_builder import polish_channel_post
from publisher.public_renderer import (
    extract_why_it_matters,
    format_why_it_matters_block,
    primary_source_handle,
    split_headline_and_body,
    strip_internal_debug_text,
)
from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output

_CTA_LINE = "Подписывайтесь на канал — главные новости без шума."
_EMOJI_SPAM = re.compile(r"([\U0001F300-\U0001FAFF\u2600-\u27BF]){4,}")
_TABLOID = re.compile(r"(шокирующ|сенсаци|вы\s+не\s+поверите|срочно\s+узнай)", re.I)

_STRIP_SOURCE_LINE = re.compile(r"^(Источник|Source|via)\s*:", re.I)
_INLINE_SOURCE = re.compile(r"(Источник|Source|via)\s*:\s*@?\w+", re.I)


def _parse_source_channels(sources: str | list[dict[str, Any]] | None) -> list[str]:
    if isinstance(sources, list):
        return [str(r.get("channel") or "") for r in sources if isinstance(r, dict) and r.get("channel")]
    try:
        data = json.loads(sources or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x.get("channel") or "") for x in data if isinstance(x, dict) and x.get("channel")]


def _strip_embedded_source_lines(text: str) -> str:
    t = _INLINE_SOURCE.sub("", text or "")
    lines = []
    for ln in t.splitlines():
        if _STRIP_SOURCE_LINE.match(ln.strip()):
            continue
        lines.append(ln)
    return re.sub(r"\s{2,}", " ", "\n".join(lines)).strip()


def _dedupe_source_lines(text: str) -> str:
    lines = (text or "").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith(("источник:", "via ", "source:")):
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
        out.append(ln)
    return "\n".join(out).strip()


def _light_tone_cleanup(text: str) -> str:
    tuning = get_editorial_tuning()
    t = _EMOJI_SPAM.sub("", text or "")
    if tuning.voice.strip_tabloid and _TABLOID.search(t):
        t = _TABLOID.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _prepare_body_plain(content: str, *, max_chars: int) -> str:
    scrubbed = scrub_publish_plaintext(content)
    cleaned = strip_internal_debug_text(scrubbed)
    return _light_tone_cleanup(polish_channel_post(cleaned, max_chars=max_chars))


def format_public_post_plain(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    why_it_matters: str | None = None,
    include_cta: bool | None = None,
    runtime_dir: str | None = None,
    max_total_chars: int = 12000,
) -> str:
    tuning = get_editorial_tuning()
    max_body = tuning.structure.summary_max_chars
    chans = _parse_source_channels(sources)
    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    polished = _prepare_body_plain(content, max_chars=max_body)
    polished = _strip_embedded_source_lines(polished)
    if attr.strip_urls_from_body:
        polished = strip_raw_urls(polished)
    headline, body = split_headline_and_body(polished)
    body, embedded_why = extract_why_it_matters(body)
    why = (why_it_matters or embedded_why or "").strip()
    story = format_public_story(headline, body, why_it_matters=why)
    parts: list[str] = []
    if story.headline:
        parts.append(story.headline)
    if story.summary:
        parts.append(story.summary)
    if story.why_it_matters:
        parts.append("")
        parts.append(format_why_it_matters_block(story.why_it_matters))
    handle_footer = primary_source_handle(sources)
    footer = apply_attribution_to_footer(
        format_source_footer_plain(handle_footer) if handle_footer else None,
        attr,
    )
    if footer:
        parts.append("")
        parts.append(footer)
    use_cta = tuning.structure.include_cta if include_cta is None else include_cta
    if use_cta:
        parts.append("")
        parts.append(_CTA_LINE)
    out = _dedupe_source_lines("\n".join(parts).strip())
    if len(out) > max_total_chars:
        out = out[: max_total_chars - 1].rstrip() + "…"
    return out


def format_source_footer_plain(handle: str | None) -> str:
    tuning = get_editorial_tuning()
    if tuning.attribution.style == "hidden":
        return ""
    h = (handle or "").strip()
    if not h:
        return ""
    if not h.startswith("@"):
        h = f"@{h.lstrip('@')}"
    if tuning.attribution.style == "via":
        return f"via {h}"
    return f"Источник: {h}"


def format_public_post_html(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    draft_id: int | None = None,
    why_it_matters: str | None = None,
    include_cta: bool | None = None,
    runtime_dir: str | None = None,
    max_total_chars: int = 12000,
) -> str:
    _ = draft_id
    tuning = get_editorial_tuning()
    max_body = tuning.structure.summary_max_chars
    chans = _parse_source_channels(sources)
    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    polished = _prepare_body_plain(content, max_chars=max_body)
    polished = _strip_embedded_source_lines(polished)
    if attr.strip_urls_from_body:
        polished = strip_raw_urls(polished)
    headline, body = split_headline_and_body(polished)
    body, embedded_why = extract_why_it_matters(body)
    why = (why_it_matters or embedded_why or "").strip()
    story = format_public_story(headline, body, why_it_matters=why)
    parts: list[str] = []
    if story.headline:
        parts.append(f"<b>{escape_telegram_html(story.headline)}</b>")
    if story.summary:
        paras = [p.strip() for p in story.summary.split("\n\n") if p.strip()]
        parts.append("\n\n".join(escape_telegram_html(p) for p in paras))
    if story.why_it_matters:
        parts.append(
            f"<i>{escape_telegram_html('Почему это важно:')}</i>\n"
            f"{escape_telegram_html(story.why_it_matters)}"
        )
    handle = primary_source_handle(sources)
    footer = apply_attribution_to_footer(
        format_source_footer_plain(handle) if handle else None,
        attr,
    )
    if footer:
        parts.append(f"<i>{escape_telegram_html(footer)}</i>")
    use_cta = tuning.structure.include_cta if include_cta is None else include_cta
    if use_cta:
        parts.append(f"<i>{escape_telegram_html(_CTA_LINE)}</i>")
    out = sanitize_telegram_html_output("\n\n".join(p for p in parts if p))
    if len(out) > max_total_chars:
        out = out[: max_total_chars - 20].rstrip() + "\n<i>…</i>"
    return out
