from __future__ import annotations

import html
import logging
from collections.abc import Sequence

from bot.config import bootstrap_env, get_openai_api_key, get_openai_model
from bot.processing.media import MediaInfo, select_digest_hero_media
from bot.editorial.digest_ranker import DigestStorySection, format_story_sections_html
from bot.storage.digest_repository import DIGEST_HOURLY, DIGEST_MORNING, DigestCandidate

logger = logging.getLogger(__name__)

MORNING_MAX_ITEMS = 10
HOURLY_MAX_ITEMS = 5

_DIGEST_TITLES = {
    DIGEST_MORNING: "Morning News Digest",
    DIGEST_HOURLY: "Hourly News Digest",
}

_DIGEST_TITLES_I18N: dict[str, dict[str, str]] = {
    DIGEST_MORNING: {
        "ru": "Утренний дайджест новостей",
    },
    DIGEST_HOURLY: {
        "ru": "Часовой дайджест новостей",
    },
}


def dedupe_by_cluster(candidates: Sequence[DigestCandidate]) -> list[DigestCandidate]:
    """Keep highest-priority item per cluster (input should already be sorted)."""
    selected: list[DigestCandidate] = []
    seen_clusters: set[int] = set()
    seen_singletons: set[int] = set()

    for item in candidates:
        if item.cluster_id is not None:
            if item.cluster_id in seen_clusters:
                continue
            seen_clusters.add(item.cluster_id)
            selected.append(item)
            continue
        if item.id in seen_singletons:
            continue
        seen_singletons.add(item.id)
        selected.append(item)
    return selected


def _collect_top_tags(items: Sequence[DigestCandidate], *, limit: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for item in items:
        for tag in item.tags:
            token = str(tag).strip().lstrip("#").lower()
            if not token:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [tag for tag, _ in ranked[:limit]]


def _format_tag_footer(tags: Sequence[str]) -> str:
    if not tags:
        return ""
    tokens = [
        f"#{html.escape(str(tag).lstrip('#').replace(' ', '_'))}"
        for tag in tags
        if str(tag).strip()
    ]
    return "\n".join(["", " ".join(tokens)]) if tokens else ""


def _truncate_summary(summary: str | None, *, max_len: int = 220) -> str:
    text = html.escape((summary or "").strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return (cut.rstrip(".,;:") + "…") if cut else text[:max_len]


def _format_digest_intelligence_block(intelligence: dict[str, str | None]) -> str:
    lines: list[str] = []
    story = intelligence.get("most_engaged_story")
    topic = intelligence.get("trending_topic")
    entity = intelligence.get("top_entity")
    if story:
        lines.extend(["🔥 Most engaged story:", html.escape(story), ""])
    if topic:
        lines.extend([f"📈 Trending topic: {html.escape(topic)}", ""])
    if entity:
        lines.extend([f"🏆 Top entity: {html.escape(entity)}", ""])
    if not lines:
        return ""
    return "\n".join(lines).strip()


def _format_trending_block(trending_entities: Sequence[str]) -> str:
    names = [name.strip() for name in trending_entities if str(name).strip()]
    if not names:
        return ""
    lines = ["🔥 Trending:", ""]
    lines.extend(f"- {html.escape(name)}" for name in names[:6])
    return "\n".join(lines)


def digest_title_for_language(digest_type: str, language: str | None) -> str:
    lang = (language or "en").strip().lower()
    if lang == "en":
        return _DIGEST_TITLES.get(digest_type, "News Digest")
    localized = _DIGEST_TITLES_I18N.get(digest_type, {}).get(lang)
    return localized or _DIGEST_TITLES.get(digest_type, "News Digest")


def format_digest_body(
    *,
    digest_type: str,
    items: Sequence[DigestCandidate],
    intro: str | None = None,
    trending_entities: Sequence[str] | None = None,
    digest_intelligence: dict[str, str | None] | None = None,
    language: str | None = None,
    story_sections: Sequence[DigestStorySection] | None = None,
) -> tuple[str, str]:
    """Return (title, html content) for Telegram."""
    headline = digest_title_for_language(digest_type, language)
    title = headline
    lines = [f"🗞 {html.escape(headline)}", ""]

    if intro:
        lines.extend([html.escape(intro.strip()), ""])

    intelligence_block = _format_digest_intelligence_block(digest_intelligence or {})
    if intelligence_block:
        lines.extend([intelligence_block, ""])

    trending_block = _format_trending_block(trending_entities or [])
    if trending_block:
        lines.extend([trending_block, ""])

    if story_sections:
        narrative_block = format_story_sections_html(list(story_sections))
        if narrative_block:
            lines.extend([narrative_block, ""])

    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {html.escape(item.title)}")
        summary = _truncate_summary(item.summary)
        if summary:
            lines.append(summary)
        lines.append("")

    tag_footer = _format_tag_footer(_collect_top_tags(items))
    if tag_footer:
        lines.append(tag_footer.strip())

    content = "\n".join(lines).strip()
    return title, content


async def _optional_openai_intro(digest_type: str, items: Sequence[DigestCandidate]) -> str | None:
    api_key = get_openai_api_key()
    if not api_key or not items:
        return None

    try:
        from openai import AsyncOpenAI

        headlines = "; ".join(item.title for item in items[:5])
        client = AsyncOpenAI(api_key=api_key, timeout=8.0, max_retries=0)
        response = await client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Write one factual sentence introducing a Telegram news digest. "
                        "No emojis, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Digest type: {digest_type}\n"
                        f"Stories: {headlines}\n"
                        "One sentence intro only."
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=80,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()
    except Exception:
        logger.exception("event=digest_intro_llm_failed digest_type=%r", digest_type)
    return None


async def generate_digest(
    digest_type: str,
    candidates: Sequence[DigestCandidate],
    *,
    max_items: int | None = None,
    use_llm_intro: bool = True,
    trending_entities: Sequence[str] | None = None,
    digest_intelligence: dict[str, str | None] | None = None,
    language: str | None = None,
    story_sections: Sequence[DigestStorySection] | None = None,
) -> dict[str, object] | None:
    """
    Build digest payload from published candidates.

    Returns None when no items remain after dedupe/limit.
    """
    bootstrap_env()
    limit = max_items
    if limit is None:
        limit = MORNING_MAX_ITEMS if digest_type == DIGEST_MORNING else HOURLY_MAX_ITEMS

    ordered = sorted(
        candidates,
        key=lambda item: (item.priority_score, item.created_at),
        reverse=True,
    )
    deduped = dedupe_by_cluster(ordered)
    selected = deduped[:limit]
    if not selected:
        return None

    intro = None
    if use_llm_intro:
        try:
            intro = await _optional_openai_intro(digest_type, selected)
        except Exception:
            logger.exception("event=digest_intro_failed digest_type=%r", digest_type)

    title, content = format_digest_body(
        digest_type=digest_type,
        items=selected,
        intro=intro,
        trending_entities=trending_entities,
        digest_intelligence=digest_intelligence,
        language=language,
        story_sections=story_sections,
    )
    hero_candidates = [
        MediaInfo(
            media_type=item.media_type,
            media_url=item.media_url,
            thumbnail_url=item.thumbnail_url,
            width=item.media_width,
            height=item.media_height,
        )
        for item in selected
    ]
    hero_media = select_digest_hero_media(hero_candidates)

    return {
        "digest_type": digest_type,
        "title": title,
        "content": content,
        "items": selected,
        "item_count": len(selected),
        "pending_news_ids": [item.id for item in selected],
        "hero_media": hero_media,
    }
