"""Unified public channel post layout (headline → body → why → source)."""

from __future__ import annotations

import re
from typing import Any

from app.editorial.public_format import format_public_story
from app.editorial.source_attribution import apply_attribution_to_footer, resolve_source_attribution
from publisher.public_renderer import (
    extract_why_it_matters,
    format_why_it_matters_block,
    primary_source_handle,
    split_headline_and_body,
)
from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output

_LEAD_EMOJI = re.compile(
    r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+\s*",
    re.UNICODE,
)


def normalize_lead_emoji(text: str) -> str:
    t = (text or "").strip()
    while True:
        n = _LEAD_EMOJI.sub("", t, count=1).strip()
        if n == t:
            break
        t = n
    return t


def render_public_post_html(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    why_it_matters: str | None = None,
    signature_line: str | None = None,
    intro_hook: str | None = None,
    runtime_dir: str | None = None,
    include_cta: bool = False,
    cta_line: str = "Подписывайтесь на канал — главные новости без шума.",
    hashtags_line: str | None = None,
    brand_footer_line: str | None = None,
    share_nudge_line: str | None = None,
    growth_meta: dict[str, Any] | None = None,
) -> str:
    """
    Standard channel HTML:
    1) Bold headline
    2) One or more body paragraphs
    3) Optional «Почему это важно»
    4) Source footer (italic)
    5) Optional CTA
    """
    from app.editorial.public_post_formatter import format_source_footer_plain

    polished = normalize_lead_emoji(content or "")
    headline, body = split_headline_and_body(polished)
    body, embedded_why = extract_why_it_matters(body)
    why = (why_it_matters or embedded_why or "").strip()
    story = format_public_story(headline, body, why_it_matters=why, growth_meta=growth_meta)

    parts: list[str] = []
    sig = (signature_line or "").strip()
    if sig:
        parts.append(f"<i>{escape_telegram_html(sig)}</i>")
    if story.headline:
        parts.append(f"<b>{escape_telegram_html(story.headline)}</b>")
    hook = (intro_hook or "").strip()
    if hook:
        parts.append(escape_telegram_html(hook))
    if story.summary:
        paras = [p.strip() for p in story.summary.split("\n\n") if p.strip()]
        parts.append("\n\n".join(escape_telegram_html(p) for p in paras))
    if story.why_it_matters:
        parts.append(
            f"<i>{escape_telegram_html('Почему это важно:')}</i>\n"
            f"{escape_telegram_html(story.why_it_matters)}"
        )
    chans: list[str] = []
    if isinstance(sources, list):
        chans = [str(r.get("channel") or "") for r in sources if isinstance(r, dict) and r.get("channel")]
    else:
        try:
            import json

            data = json.loads(sources or "[]")
            if isinstance(data, list):
                chans = [str(x.get("channel") or "") for x in data if isinstance(x, dict) and x.get("channel")]
        except (json.JSONDecodeError, TypeError):
            chans = []
    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    handle = primary_source_handle(sources)
    footer = apply_attribution_to_footer(
        format_source_footer_plain(handle) if handle else None,
        attr,
    )
    if footer:
        parts.append(f"<i>{escape_telegram_html(footer)}</i>")
    tags = (hashtags_line or "").strip()
    if tags:
        parts.append(escape_telegram_html(tags))
    brand = (brand_footer_line or "").strip()
    if brand:
        parts.append(f"<i>{escape_telegram_html(brand)}</i>")
    if include_cta and cta_line.strip():
        parts.append(f"<i>{escape_telegram_html(cta_line.strip())}</i>")
    share = (share_nudge_line or "").strip()
    if share:
        parts.append(f"<i>{escape_telegram_html(share)}</i>")
    return sanitize_telegram_html_output("\n\n".join(p for p in parts if p))
