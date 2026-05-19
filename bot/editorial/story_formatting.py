from __future__ import annotations

import html
from datetime import datetime

from bot.editorial.importance import importance_tier
from bot.editorial.timeline import compact_timeline_lines
from bot.editorial.story_types import StorySnapshot
from bot.storage.story_repository import StoryTimelineEntry


def _escape(text: str) -> str:
    return html.escape(text.strip())


def format_story_line(story: StorySnapshot, *, index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    tier = importance_tier(story.importance_score)
    velocity = f"v={story.trend_velocity:.2f}"
    return (
        f"{prefix}#{story.id} {_escape(story.title)}\n"
        f"   status={story.status} tier={tier} imp={story.importance_score:.2f} "
        f"nov={story.novelty_score:.2f} {velocity}"
    )


def format_story_detail(
    story: StorySnapshot,
    *,
    timeline: list[StoryTimelineEntry],
) -> str:
    lines = [
        f"*Story #{story.id}*",
        _escape(story.title),
        "",
        f"Status: `{story.status}`",
        f"Importance: {story.importance_score:.2f} ({importance_tier(story.importance_score)})",
        f"Novelty: {story.novelty_score:.2f} | Velocity: {story.trend_velocity:.2f}",
        f"Sources: {story.source_count} | Clusters: {story.cluster_count}",
    ]
    if story.canonical_summary:
        lines.extend(["", _escape(story.canonical_summary)])
    if story.entity_names:
        lines.extend(["", "Entities: " + ", ".join(_escape(n) for n in story.entity_names[:8])])
    if story.geopolitical_tags:
        lines.extend(["Geo tags: " + ", ".join(story.geopolitical_tags)])
    tl_lines = compact_timeline_lines(timeline, limit=10)
    if tl_lines:
        lines.extend(["", "*Timeline*", *[f"• {_escape(line)}" for line in tl_lines]])
    return "\n".join(lines)


def format_story_list(
    stories: list[StorySnapshot],
    *,
    title: str,
    page: int = 0,
    page_size: int = 8,
) -> str:
    if not stories:
        return f"{title}\n\nNo stories in registry."
    start = page * page_size
    chunk = stories[start : start + page_size]
    lines = [title, ""]
    for idx, story in enumerate(chunk, start=start + 1):
        lines.append(format_story_line(story, index=idx))
    total_pages = max(1, (len(stories) + page_size - 1) // page_size)
    lines.append(f"\nPage {page + 1}/{total_pages} — {len(stories)} total")
    return "\n".join(lines)


def format_lifecycle_summary(counts: dict[str, int]) -> str:
    if not counts:
        return "Narrative registry empty."
    parts = [f"{status}: {count}" for status, count in sorted(counts.items())]
    return "Story lifecycle — " + ", ".join(parts)
