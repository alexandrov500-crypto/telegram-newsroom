from __future__ import annotations

import html
import os
from dataclasses import dataclass

from bot.editorial.formatting import TELEGRAM_CAPTION_MAX, TELEGRAM_MESSAGE_MAX
from bot.editorial.media_enrichment import enrich_publish_media
from bot.editorial.multilingual_publish import resolve_localized_publish_text
from bot.editorial.presentation import (
    build_publish_presentation,
    format_presentation_html,
)
from bot.processing.headlines import CAPTION_HYBRID
from bot.processing.languages import LANG_EN
from bot.runtime.state import runtime_state
from bot.editorial.memory.analyzer import analyze_editorial_memory
from bot.editorial.memory.service import get_editorial_memory_repo
from bot.editorial.memory.types import EditorialMemoryReport
from bot.editorial.priority.scoring import EditorialPriorityResult
from bot.editorial.priority.service import evaluate_item_priority
from bot.editorial.quality.evaluator import EditorialQualityReport, evaluate_pending_item
from bot.editorial.quality.service import get_editorial_quality_repo
from bot.storage.editorial_repository import PendingNewsItem
from bot.storage.localization_repository import LocalizationRepository


@dataclass(frozen=True, slots=True)
class PostPreview:
    pending_news_id: int
    language: str
    template_key: str
    html_message: str
    html_caption: str
    message_len: int
    caption_len: int
    caption_truncated: bool
    media_type: str
    media_url: str | None
    media_enriched: bool
    canonical_link: str
    source_display: str
    editorial_quality_score: float | None = None
    quality_warnings: tuple[str, ...] = ()
    quality_fatigue: dict[str, float] | None = None
    quality_dimensions: dict[str, float] | None = None
    storyline_id: str | None = None
    follow_up_kind: str | None = None
    context_snippet: str | None = None
    memory_warnings: tuple[str, ...] = ()
    memory_saturation: float | None = None
    framing_hint: str | None = None
    editorial_priority_score: float | None = None
    urgency_class: str | None = None
    priority_warnings: tuple[str, ...] = ()
    why_ranked: tuple[str, ...] = ()


async def build_post_preview(
    item: PendingNewsItem,
    *,
    language: str = LANG_EN,
    localizations: LocalizationRepository | None = None,
    fetch_media: bool | None = None,
) -> PostPreview:
    """Assemble final Telegram HTML and media metadata without publishing."""
    if fetch_media is None:
        raw = os.getenv("EDITORIAL_PREVIEW_FETCH_MEDIA", "false").strip().lower()
        fetch_media = raw in ("1", "true", "yes", "on")

    text = resolve_localized_publish_text(item, language, localizations)
    media_type = item.media_type
    media_url = item.media_url
    media_enriched = False

    if fetch_media:
        media = await enrich_publish_media(item)
        if media.has_media:
            media_type = media.media_type
            media_url = media.media_url
            media_enriched = True
    elif item.media_url:
        media_enriched = False

    pres = build_publish_presentation(
        title=text.headline,
        summary=text.summary or "",
        link=item.link,
        tags=item.tags,
        source=item.source,
        hook_line=text.hook,
        original_title=text.original_title,
        show_original_subtitle=runtime_state.caption_style == CAPTION_HYBRID,
    )
    html_message = format_presentation_html(pres, max_len=TELEGRAM_MESSAGE_MAX)
    html_caption = format_presentation_html(pres, max_len=TELEGRAM_CAPTION_MAX)

    quality: EditorialQualityReport | None = None
    try:
        repo = get_editorial_quality_repo()
        quality = evaluate_pending_item(
            item,
            headline=text.headline,
            summary=text.summary or "",
            hook_line=text.hook,
            repo=repo,
        )
    except Exception:
        quality = None

    memory: EditorialMemoryReport | None = None
    try:
        mem_repo = get_editorial_memory_repo()
        memory = analyze_editorial_memory(
            headline=text.headline,
            summary=text.summary or "",
            tags=list(item.tags or []),
            source=item.source,
            repo=mem_repo,
            cluster_id=item.cluster_id,
        )
    except Exception:
        memory = None

    priority: EditorialPriorityResult | None = None
    try:
        priority = evaluate_item_priority(item)
    except Exception:
        priority = None

    return PostPreview(
        pending_news_id=item.id,
        language=language,
        template_key=pres.template.key,
        html_message=html_message,
        html_caption=html_caption,
        message_len=len(html_message),
        caption_len=len(html_caption),
        caption_truncated=len(html_message) > TELEGRAM_CAPTION_MAX,
        media_type=media_type,
        media_url=media_url,
        media_enriched=media_enriched,
        canonical_link=pres.canonical_link,
        source_display=pres.source_display,
        editorial_quality_score=quality.editorial_quality_score if quality else None,
        quality_warnings=quality.warnings if quality else (),
        quality_fatigue=quality.fatigue if quality else None,
        quality_dimensions=quality.dimensions if quality else None,
        storyline_id=memory.storyline_id if memory else None,
        follow_up_kind=memory.follow_up_kind if memory else None,
        context_snippet=memory.context_snippet if memory else None,
        memory_warnings=memory.warnings if memory else (),
        memory_saturation=memory.saturation_score if memory else None,
        framing_hint=memory.framing_hint if memory else None,
        editorial_priority_score=priority.editorial_priority_score if priority else None,
        urgency_class=priority.urgency_class if priority else None,
        priority_warnings=priority.warnings if priority else (),
        why_ranked=priority.why_ranked if priority else (),
    )


def format_preview_operator_html(preview: PostPreview) -> str:
    media_line = "none"
    if preview.media_url:
        media_line = f"{preview.media_type} · {preview.media_url[:72]}…"
        if len(preview.media_url) <= 72:
            media_line = f"{preview.media_type} · {preview.media_url}"
    enrich = "yes" if preview.media_enriched else "no"
    lines = [
        f"<b>Post preview</b> #{preview.pending_news_id}",
        f"Template: <code>{preview.template_key}</code> · lang: <code>{preview.language}</code>",
        f"Source: <b>{preview.source_display}</b>",
        f"Link: <code>{preview.canonical_link[:120]}</code>",
        f"Media ({enrich}): {media_line}",
        f"Len: message={preview.message_len} caption={preview.caption_len}"
        f"{' · caption truncated' if preview.caption_truncated else ''}",
    ]
    if preview.editorial_quality_score is not None:
        lines.append(
            f"Editorial quality: <b>{preview.editorial_quality_score:.2f}</b>",
        )
    if preview.quality_warnings:
        lines.append("\n<b>Quality warnings</b>")
        for warning in preview.quality_warnings:
            lines.append(f"⚠ {html.escape(warning)}")
    if preview.quality_fatigue:
        fat = preview.quality_fatigue
        lines.append(
            "\nFatigue: "
            f"topic={fat.get('topic_fatigue', 0):.2f} "
            f"source={fat.get('source_fatigue', 0):.2f} "
            f"template={fat.get('template_fatigue', 0):.2f} "
            f"tone={fat.get('tone_fatigue', 0):.2f}",
        )
    if preview.storyline_id:
        lines.append(
            f"\n<b>Narrative memory</b>\n"
            f"Storyline: <code>{html.escape(preview.storyline_id)}</code> · "
            f"type: <code>{html.escape(preview.follow_up_kind or '—')}</code>",
        )
        if preview.context_snippet:
            lines.append(f"<i>Context:</i> {html.escape(preview.context_snippet)}")
        if preview.memory_saturation is not None:
            lines.append(f"Storyline saturation: {preview.memory_saturation:.2f}")
        if preview.framing_hint:
            lines.append(f"<i>Framing hint:</i> {html.escape(preview.framing_hint)}")
    if preview.memory_warnings:
        lines.append("\n<b>Narrative warnings</b>")
        for warning in preview.memory_warnings:
            lines.append(f"⚠ {html.escape(warning)}")
    if preview.editorial_priority_score is not None:
        lines.append(
            f"\n<b>Editorial priority</b> "
            f"<code>{preview.editorial_priority_score:.2f}</code> "
            f"[{html.escape(preview.urgency_class or '—')}]",
        )
        if preview.why_ranked:
            lines.append(f"<i>Why:</i> {html.escape('; '.join(preview.why_ranked[:3]))}")
    if preview.priority_warnings:
        lines.append("<b>Priority warnings</b>")
        for warning in preview.priority_warnings:
            lines.append(f"⚠ {html.escape(warning)}")
    lines.append(f"\n<b>Telegram HTML (message)</b>\n<pre>{_escape_pre(preview.html_message)}</pre>")
    return "\n".join(lines)


def _escape_pre(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )[:3500]
