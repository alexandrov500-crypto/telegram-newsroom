from __future__ import annotations

import html
import os
from collections.abc import Sequence
from dataclasses import dataclass

from bot.editorial.hashtags import format_hashtag_line, normalize_hashtags
from bot.editorial.links import canonical_article_url
from bot.editorial.source_registry import resolve_source_display
from bot.editorial.templates import EditorialTemplate, resolve_editorial_template

TELEGRAM_CAPTION_MAX = 1024
TELEGRAM_MESSAGE_MAX = 4096


@dataclass(frozen=True, slots=True)
class PublishPresentation:
    template: EditorialTemplate
    headline: str
    summary: str
    hook: str | None
    canonical_link: str
    tags: tuple[str, ...]
    source_key: str | None
    source_display: str
    source_short: str
    source_emoji: str
    trending_entities: tuple[str, ...]
    show_original_subtitle: bool
    original_title: str | None


def build_publish_presentation(
    *,
    title: str,
    summary: str,
    link: str,
    tags: Sequence[str],
    source: str | None = None,
    trending_entities: Sequence[str] | None = None,
    hook_line: str | None = None,
    original_title: str | None = None,
    show_original_subtitle: bool = False,
    template_key: str | None = None,
) -> PublishPresentation:
    template = resolve_editorial_template(
        source=source,
        tags=tags,
        override=template_key or os.getenv("EDITORIAL_TEMPLATE") or None,
    )
    src = resolve_source_display(source)
    clean_link = canonical_article_url(link)
    norm_tags = tuple(normalize_hashtags(tags, source=source))
    hook = (hook_line or "").strip() or None

    return PublishPresentation(
        template=template,
        headline=title.strip(),
        summary=(summary or "").strip(),
        hook=hook,
        canonical_link=clean_link,
        tags=norm_tags,
        source_key=src.key,
        source_display=src.name,
        source_short=src.short,
        source_emoji=src.emoji,
        trending_entities=tuple(
            str(n).strip() for n in (trending_entities or ()) if str(n).strip()
        )[:4],
        show_original_subtitle=show_original_subtitle,
        original_title=(original_title or "").strip() or None,
    )


def _format_trending_block(entities: Sequence[str]) -> str:
    names = [html.escape(n) for n in entities if n][:4]
    if not names:
        return ""
    return f"<i>Trending:</i> {', '.join(names)}"


def _render_presentation_lines(
    presentation: PublishPresentation,
    *,
    summary_override: str | None = None,
) -> list[str]:
    p = presentation
    t = p.template
    lines: list[str] = []

    headline_esc = html.escape(p.headline)
    lines.append(f"{t.headline_emoji} <b>{headline_esc}</b>")

    if (
        p.show_original_subtitle
        and p.original_title
        and p.original_title != p.headline
    ):
        lines.append(f"<i>{html.escape(p.original_title)}</i>")

    summary = summary_override if summary_override is not None else p.summary
    if summary:
        lines.append("")
        lines.append(html.escape(summary))

    if p.hook and p.hook != p.headline:
        lines.append("")
        lines.append(f"<i>{html.escape(t.insight_label)}:</i> {html.escape(p.hook)}")

    trending = _format_trending_block(p.trending_entities)
    if trending:
        lines.append("")
        lines.append(trending)

    lines.append("")
    src_label = p.source_display
    if p.source_short and p.source_short.upper() != p.source_display.upper():
        src_label = f"{p.source_display} ({p.source_short})"
    lines.append(
        f"{p.source_emoji} <i>{html.escape(t.source_prefix)}:</i> "
        f"<b>{html.escape(src_label)}</b>",
    )

    tag_line = format_hashtag_line(p.tags)
    if tag_line:
        lines.append("")
        lines.append(tag_line)

    if p.canonical_link:
        safe_href = html.escape(p.canonical_link, quote=True)
        read_label = "Read more"
        if p.source_short:
            read_label = f"Read more at {p.source_short}"
        lines.append("")
        lines.append(f'<a href="{safe_href}">{html.escape(read_label)} →</a>')

    return lines


def format_presentation_html(
    presentation: PublishPresentation,
    *,
    max_len: int = TELEGRAM_MESSAGE_MAX,
) -> str:
    """Telegram HTML body: headline → summary → context → source → tags → read link."""
    summary = presentation.summary
    if summary:
        words = summary.split()
        for _ in range(24):
            body = "\n".join(_render_presentation_lines(presentation, summary_override=summary))
            if len(body) <= max_len:
                return body
            if len(words) <= 8:
                break
            words = words[: max(8, int(len(words) * 0.82))]
            summary = " ".join(words)
            if summary and not summary.endswith("…"):
                summary = summary.rstrip() + "…"

    body = "\n".join(_render_presentation_lines(presentation, summary_override=summary or None))
    return truncate_html_safe(body, max_len)


def truncate_html_safe(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    trimmed = text[: max_len - 1]
    last_amp = trimmed.rfind("&")
    last_semi = trimmed.rfind(";")
    if last_amp > len(trimmed) - 8 and (last_semi < last_amp or last_semi < len(trimmed) - 6):
        trimmed = trimmed[:last_amp]
    return trimmed.rstrip() + "…"


def format_publish_caption(
    *,
    title: str,
    summary: str,
    link: str,
    tags: Sequence[str],
    source: str | None = None,
    trending_entities: Sequence[str] | None = None,
    hook_line: str | None = None,
    original_title: str | None = None,
    show_original_subtitle: bool = False,
    max_len: int = TELEGRAM_CAPTION_MAX,
    template_key: str | None = None,
) -> str:
    pres = build_publish_presentation(
        title=title,
        summary=summary,
        link=link,
        tags=tags,
        source=source,
        trending_entities=trending_entities,
        hook_line=hook_line,
        original_title=original_title,
        show_original_subtitle=show_original_subtitle,
        template_key=template_key,
    )
    return format_presentation_html(pres, max_len=max_len)


def format_publish_message(
    *,
    title: str,
    summary: str,
    link: str,
    tags: Sequence[str],
    source: str | None = None,
    trending_entities: Sequence[str] | None = None,
    hook_line: str | None = None,
    original_title: str | None = None,
    show_original_subtitle: bool = False,
    max_len: int = TELEGRAM_MESSAGE_MAX,
    template_key: str | None = None,
) -> str:
    return format_publish_caption(
        title=title,
        summary=summary,
        link=link,
        tags=tags,
        source=source,
        trending_entities=trending_entities,
        hook_line=hook_line,
        original_title=original_title,
        show_original_subtitle=show_original_subtitle,
        max_len=max_len,
        template_key=template_key,
    )


def format_enriched_message(enriched: dict, link: str, *, source: str | None = None) -> str:
    return format_publish_message(
        title=str(enriched.get("title", "")),
        summary=str(enriched.get("summary", "")),
        link=link,
        tags=enriched.get("tags") or [],
        source=source or enriched.get("source"),
    )

