from __future__ import annotations

import json
from collections.abc import Sequence

from bot.editorial.presentation import (
    TELEGRAM_CAPTION_MAX,
    TELEGRAM_MESSAGE_MAX,
    build_publish_presentation,
    format_enriched_message,
    format_publish_caption,
    format_publish_message,
    truncate_html_safe,
)
from bot.processing.media import MEDIA_NONE

# Re-export presentation API (legacy import path).
__all__ = [
    "TELEGRAM_CAPTION_MAX",
    "TELEGRAM_MESSAGE_MAX",
    "build_publish_presentation",
    "format_publish_caption",
    "format_publish_message",
    "format_enriched_message",
    "truncate_html_safe",
    "parse_tags_field",
    "format_tag_line",
    "format_pending_queue_item",
]


def parse_tags_field(tags: str | None) -> list[str]:
    if not tags:
        return []
    try:
        parsed = json.loads(tags)
        if isinstance(parsed, list):
            return [str(t) for t in parsed if str(t).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in tags.split(",") if part.strip()]


def format_tag_line(tags: Sequence[str]) -> str:
    from bot.editorial.hashtags import format_hashtag_line

    return format_hashtag_line(tags)


def format_pending_queue_item(
    *,
    news_id: int,
    title: str,
    tags: Sequence[str],
    sources: Sequence[str] = (),
    variant_count: int = 1,
    priority_score: float = 0.5,
    priority_reason: str | None = None,
    media_type: str = MEDIA_NONE,
    entity_names: Sequence[str] = (),
    optimized_headline: str | None = None,
    hook_line: str | None = None,
) -> str:
    from bot.editorial.source_registry import format_source_attribution

    lines = [f"#{news_id} [{priority_score:.2f}]", title]
    if optimized_headline and optimized_headline.strip() != title.strip():
        lines.append(f"Optimized: {optimized_headline.strip()}")
    if hook_line:
        lines.append(f"Hook: {hook_line.strip()}")
    if media_type and media_type != MEDIA_NONE:
        lines.append(f"Media: {media_type}")
    if entity_names:
        lines.append(f"Entities: {', '.join(entity_names)}")
    if priority_reason:
        lines.append(f"Reason: {priority_reason}")
    if sources:
        formatted = [format_source_attribution(s) for s in sources]
        lines.append(f"Sources: {', '.join(formatted)}")
    elif len(sources) == 0:
        pass
    if variant_count > 1:
        lines.append(f"Variants: {variant_count}")
    if tags:
        tag_line = format_tag_line(tags)
        if tag_line:
            lines.append(f"Tags: {tag_line}")
    return "\n".join(lines)
