from __future__ import annotations

import html
import re
from dataclasses import dataclass

from bot.editorial.importance import importance_tier
from bot.editorial.story_types import StorySnapshot
from bot.editorial.timeline import compact_timeline_lines
from bot.storage.story_repository import StoryRepository

_TECH_RE = re.compile(r"\b(ai|openai|nvidia|chip|llm|startup|tech)\b", re.I)
_MARKET_RE = re.compile(
    r"\b(etf|fed|bitcoin|ethereum|nasdaq|stock|market|ipo|sec|treasury)\b",
    re.I,
)
_GEO_RE = re.compile(
    r"\b(war|sanction|nato|election|invasion|ceasefire|missile|"
    r"embargo|conflict|border|ukraine|russia|china)\b",
    re.I,
)

SECTION_TOP = "top_stories"
SECTION_MARKET = "market_moves"
SECTION_GEO = "geopolitical"
SECTION_TECH = "tech_ai"
SECTION_EMERGING = "emerging"

_SECTION_TITLES = {
    SECTION_TOP: "TOP STORIES",
    SECTION_MARKET: "MARKET MOVES",
    SECTION_GEO: "GEOPOLITICAL EVENTS",
    SECTION_TECH: "TECH & AI",
    SECTION_EMERGING: "EMERGING NARRATIVES",
}


@dataclass(frozen=True)
class RankedStory:
    story: StorySnapshot
    score: float
    tier: str
    timeline_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class DigestStorySection:
    key: str
    title: str
    stories: tuple[RankedStory, ...]


def _story_text(story: StorySnapshot) -> str:
    return f"{story.title} {story.canonical_summary or ''} {' '.join(story.geopolitical_tags)}"


def classify_story(story: StorySnapshot) -> str:
    text = _story_text(story).lower()
    if story.geopolitical_tags or _GEO_RE.search(text):
        return SECTION_GEO
    if _MARKET_RE.search(text):
        return SECTION_MARKET
    if _TECH_RE.search(text):
        return SECTION_TECH
    if story.novelty_score >= 0.65 and story.cluster_count <= 2:
        return SECTION_EMERGING
    return SECTION_TOP


def rank_story(story: StorySnapshot) -> RankedStory:
    velocity_boost = min(0.2, story.trend_velocity * 0.2)
    score = min(1.0, story.importance_score * 0.7 + story.novelty_score * 0.15 + velocity_boost)
    return RankedStory(
        story=story,
        score=score,
        tier=importance_tier(story.importance_score),
    )


class DigestRanker:
    def __init__(self, registry_repo: StoryRepository) -> None:
        self._repo = registry_repo

    def build_sections(self, *, limit_per_section: int = 3) -> list[DigestStorySection]:
        candidates = self._repo.list_active_stories(limit=40)
        if not candidates:
            candidates = self._repo.list_top_by_importance(limit=15)
        ranked = sorted((rank_story(s) for s in candidates), key=lambda r: -r.score)

        buckets: dict[str, list[RankedStory]] = {key: [] for key in _SECTION_TITLES}
        for item in ranked:
            section_key = classify_story(item.story)
            if section_key == SECTION_TOP and len(buckets[SECTION_TOP]) >= limit_per_section:
                section_key = SECTION_EMERGING
            if len(buckets[section_key]) >= limit_per_section:
                continue
            timeline = tuple(
                compact_timeline_lines(
                    self._repo.timeline(item.story.id, limit=4),
                    limit=3,
                )
            )
            enriched = RankedStory(
                story=item.story,
                score=item.score,
                tier=item.tier,
                timeline_lines=timeline,
            )
            buckets[section_key].append(enriched)

        order = (
            SECTION_TOP,
            SECTION_MARKET,
            SECTION_GEO,
            SECTION_TECH,
            SECTION_EMERGING,
        )
        sections: list[DigestStorySection] = []
        for key in order:
            stories = buckets[key]
            if not stories:
                continue
            sections.append(
                DigestStorySection(
                    key=key,
                    title=_SECTION_TITLES[key],
                    stories=tuple(stories),
                ),
            )
        return sections


def format_story_sections_html(sections: list[DigestStorySection]) -> str:
    lines: list[str] = []
    for section in sections:
        lines.extend([f"<b>{html.escape(section.title)}</b>", ""])
        for idx, ranked in enumerate(section.stories, start=1):
            story = ranked.story
            lines.append(
                f"{idx}. {html.escape(story.title)} "
                f"<i>({html.escape(ranked.tier)})</i>"
            )
            if story.canonical_summary:
                summary = story.canonical_summary
                if len(summary) > 200:
                    summary = summary[:197] + "…"
                lines.append(html.escape(summary))
            for tl in ranked.timeline_lines[:2]:
                lines.append(f"  • {html.escape(tl)}")
            lines.append("")
    return "\n".join(lines).strip()
