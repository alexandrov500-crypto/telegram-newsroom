from __future__ import annotations

from dataclasses import dataclass

from bot.editorial.memory.analyzer import analyze_editorial_memory
from bot.editorial.memory.repository import EditorialMemoryRepository
from bot.editorial.multilingual_publish import resolve_localized_publish_text
from bot.editorial.priority.balance import topic_bucket
from bot.editorial.priority.scoring import EditorialPriorityResult, compute_editorial_priority
from bot.processing.languages import LANG_EN
from bot.runtime.state import runtime_state
from bot.storage.editorial_repository import PendingNewsItem
from bot.storage.source_repository import SourceRepository


@dataclass(frozen=True, slots=True)
class RankedQueueItem:
    item: PendingNewsItem
    headline: str
    priority: EditorialPriorityResult
    memory_follow_up: str | None
    storyline_id: str | None


def rank_pending_items(
    items: list[PendingNewsItem],
    *,
    memory_repo: EditorialMemoryRepository,
    sources: SourceRepository | None = None,
) -> list[RankedQueueItem]:
    recent_events = memory_repo.recent_posts(limit=25, hours=72)
    recent_buckets = [
        topic_bucket(e.get("tags") or [], None)
        for e in recent_events
    ]
    recent_headlines = [str(e.get("headline") or "") for e in recent_events]

    ranked: list[RankedQueueItem] = []
    for item in items:
        text = resolve_localized_publish_text(item, LANG_EN, None)
        headline = text.headline
        summary = text.summary or ""

        memory = analyze_editorial_memory(
            headline=headline,
            summary=summary,
            tags=list(item.tags or []),
            source=item.source,
            repo=memory_repo,
            cluster_id=item.cluster_id,
        )

        trust = 0.55
        if sources is not None and item.source:
            trust = sources.get_profile(item.source).trust_score

        sl_publish = memory.publish_count
        storyline_id = memory.storyline_id

        priority = compute_editorial_priority(
            headline=headline,
            summary=summary,
            tags=list(item.tags or []),
            source=item.source,
            source_trust=trust,
            source_count=item.source_count,
            variant_count=item.variant_count,
            sources=item.sources,
            memory_saturation=memory.saturation_score,
            memory_match_score=memory.match_score,
            follow_up_kind=memory.follow_up_kind,
            storyline_publish_count=sl_publish,
            recent_headlines=recent_headlines,
            recent_topic_buckets=recent_buckets,
        )

        ranked.append(
            RankedQueueItem(
                item=item,
                headline=headline,
                priority=priority,
                memory_follow_up=memory.follow_up_kind,
                storyline_id=storyline_id,
            ),
        )

    ranked.sort(
        key=lambda r: (
            r.priority.editorial_priority_score,
            r.item.priority_score,
        ),
        reverse=True,
    )
    return ranked
