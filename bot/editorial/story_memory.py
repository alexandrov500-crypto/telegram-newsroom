from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bot.editorial.entity_graph import EntityGraph
from bot.editorial.importance import compute_importance, recompute_story_status
from bot.editorial.narrative_detector import pick_best_story_match
from bot.editorial.novelty import compute_novelty
from bot.editorial.story_evolution import detect_story_event, is_escalation
from bot.editorial.story_registry import StoryRegistry
from bot.editorial.story_types import StoryStatus
from bot.editorial.timeline import timeline_context_block
from bot.storage.entity_repository import EntityRepository
from bot.storage.story_repository import StoryRepository

if TYPE_CHECKING:
    from bot.distributed.cluster.federation import FederatedStoryRegistry

logger = logging.getLogger(__name__)

_GEO_TAG_RE = re.compile(
    r"\b(war|sanction|nato|ukraine|russia|china|election|ceasefire|"
    r"embargo|conflict|missile|border)\b",
    re.I,
)


def extract_geopolitical_tags(text: str) -> list[str]:
    found = {match.group(0).lower() for match in _GEO_TAG_RE.finditer(text)}
    return sorted(found)[:8]


class StoryMemoryService:
    """Orchestrates narrative detection, scoring, and persistence."""

    def __init__(
        self,
        repository: StoryRepository,
        *,
        entities: EntityRepository | None = None,
        federation: FederatedStoryRegistry | None = None,
    ) -> None:
        self._repo = repository
        self._registry = StoryRegistry(repository)
        self._entities = entities
        self._graph = EntityGraph(repository)
        self._federation = federation

    @property
    def registry(self) -> StoryRegistry:
        return self._registry

    def memory_context_for_cluster(self, cluster_id: int) -> dict[str, str] | None:
        story = self._registry.story_for_cluster(cluster_id)
        if story is None:
            return None
        timeline = self._repo.timeline(story.id, limit=8)
        block = timeline_context_block(timeline)
        return {
            "story_id": str(story.id),
            "canonical_summary": story.canonical_summary or "",
            "timeline": block,
            "title": story.title,
        }

    async def process_cluster_update(
        self,
        *,
        title: str,
        summary: str | None,
        tags: list[str],
        cluster_id: int,
        pending_news_id: int | None,
        source: str | None,
        source_trust: float,
        source_count: int,
        cluster_variant_count: int,
        priority_score: float,
        languages: list[str] | None = None,
    ) -> int | None:
        started = time.perf_counter()
        try:
            return self._process_cluster_update_sync(
                title=title,
                summary=summary,
                tags=tags,
                cluster_id=cluster_id,
                pending_news_id=pending_news_id,
                source=source,
                source_trust=source_trust,
                source_count=source_count,
                cluster_variant_count=cluster_variant_count,
                priority_score=priority_score,
                languages=languages,
            )
        except Exception:
            logger.exception(
                "event=story_memory_failed cluster_id=%s pending_news_id=%s",
                cluster_id,
                pending_news_id,
            )
            return None
        finally:
            elapsed = time.perf_counter() - started
            from bot.observability.metrics import observe_narrative_detection

            observe_narrative_detection(elapsed)

    def _entity_names(
        self,
        *,
        title: str,
        summary: str | None,
        tags: list[str],
        pending_news_id: int | None,
    ) -> list[str]:
        if pending_news_id is not None and self._entities is not None:
            names = self._entities.get_entity_names_for_pending(
                pending_news_id,
                limit=12,
            )
            if names:
                return names
        tokens = [t.lstrip("#") for t in tags if t]
        return tokens[:8]

    def _process_cluster_update_sync(
        self,
        *,
        title: str,
        summary: str | None,
        tags: list[str],
        cluster_id: int,
        pending_news_id: int | None,
        source: str | None,
        source_trust: float,
        source_count: int,
        cluster_variant_count: int,
        priority_score: float,
        languages: list[str] | None,
    ) -> int | None:
        existing_id = self._repo.story_id_for_cluster(cluster_id)
        entity_names = self._entity_names(
            title=title,
            summary=summary,
            tags=tags,
            pending_news_id=pending_news_id,
        )
        entity_keys = {name.lower() for name in entity_names}

        active = self._repo.list_active_stories(limit=80)
        entity_map = self._repo.entity_map_for_stories([s.id for s in active])

        matched_story = None
        match_score = 0.0
        if existing_id is not None:
            matched_story = self._repo.get_story(existing_id)
        if matched_story is None:
            matched_story, match_score = pick_best_story_match(
                title=title,
                entity_keys=entity_keys,
                candidates=active,
                entity_map=entity_map,
            )
            if matched_story:
                logger.info(
                    "event=story_matched story_id=%s cluster_id=%s score=%.3f",
                    matched_story.id,
                    cluster_id,
                    match_score,
                )

        text_blob = f"{title} {summary or ''}"
        geo_tags = extract_geopolitical_tags(text_blob)
        lang_list = list(languages or [])

        if matched_story is None:
            importance = compute_importance(
                title=title,
                summary=summary,
                tags=tags,
                source_trust=source_trust,
                source_count=source_count,
                entity_names=entity_names,
                trend_velocity=0.35,
                language_count=len(lang_list) or 1,
                cluster_variant_count=cluster_variant_count,
                priority_score=priority_score,
            )
            novelty = compute_novelty(
                title=title,
                summary=summary,
                prior_title=None,
                prior_summary=None,
                cluster_variant_count=cluster_variant_count,
            )
            story_id = self._repo.create_story(
                title=title,
                canonical_summary=summary,
                status=StoryStatus.ACTIVE.value,
                geopolitical_tags=geo_tags,
                languages=lang_list,
                importance_score=importance.importance_score,
                novelty_score=novelty.novelty_score,
                trend_velocity=0.35,
                cluster_count=cluster_variant_count,
                source_count=source_count,
                canonical_cluster_id=cluster_id,
            )
            event = detect_story_event(
                title=title,
                summary=summary,
                prior_summary=None,
                importance_delta=importance.importance_score,
            )
            self._repo.add_event(
                story_id=story_id,
                event_type=event.type,
                significance=event.significance,
                headline=event.headline,
                summary=event.summary,
                pending_news_id=pending_news_id,
                cluster_id=cluster_id,
            )
            self._finalize_story(
                story_id=story_id,
                importance=importance.importance_score,
                novelty=novelty,
                trend_velocity=0.35,
                entity_names=entity_names,
                cluster_id=cluster_id,
                pending_news_id=pending_news_id,
                event_type=event.type,
                is_new=True,
            )
            return story_id

        story_id = matched_story.id
        prior_summary = matched_story.canonical_summary
        prior_importance = matched_story.importance_score

        novelty = compute_novelty(
            title=title,
            summary=summary,
            prior_title=matched_story.title,
            prior_summary=prior_summary,
            cluster_variant_count=cluster_variant_count,
        )
        prev_velocity = matched_story.trend_velocity
        growth = max(0, cluster_variant_count - matched_story.cluster_count)
        trend_velocity = min(1.0, prev_velocity * 0.55 + growth * 0.12 + source_count * 0.04)

        importance = compute_importance(
            title=title,
            summary=summary,
            tags=tags,
            source_trust=source_trust,
            source_count=max(source_count, matched_story.source_count),
            entity_names=entity_names,
            trend_velocity=trend_velocity,
            language_count=max(len(lang_list), 1),
            cluster_variant_count=cluster_variant_count,
            priority_score=priority_score,
        )

        hours_since = _hours_since(matched_story.last_updated_at)
        status = recompute_story_status(
            matched_story,
            trend_velocity=trend_velocity,
            importance_score=importance.importance_score,
            hours_since_update=hours_since,
        )

        merged_geo = sorted(set(matched_story.geopolitical_tags) | set(geo_tags))
        merged_langs = _merge_languages(matched_story.languages_json, lang_list)

        self._repo.update_story(
            story_id,
            title=title if importance.importance_score >= prior_importance else None,
            canonical_summary=summary or prior_summary,
            status=status,
            importance_score=importance.importance_score,
            novelty_score=novelty.novelty_score,
            trend_velocity=trend_velocity,
            cluster_count=cluster_variant_count,
            source_count=max(source_count, matched_story.source_count),
            geopolitical_tags=merged_geo,
            languages=merged_langs,
            refresh_fingerprint=True,
        )

        event = detect_story_event(
            title=title,
            summary=summary,
            prior_summary=prior_summary,
            importance_delta=importance.importance_score - prior_importance,
        )
        self._repo.add_event(
            story_id=story_id,
            event_type=event.type,
            significance=event.significance,
            headline=event.headline,
            summary=event.summary,
            pending_news_id=pending_news_id,
            cluster_id=cluster_id,
        )
        self._finalize_story(
            story_id=story_id,
            importance=importance.importance_score,
            novelty=novelty,
            trend_velocity=trend_velocity,
            entity_names=entity_names,
            cluster_id=cluster_id,
            pending_news_id=pending_news_id,
            event_type=event.type,
            is_new=False,
        )
        return story_id

    def _finalize_story(
        self,
        *,
        story_id: int,
        importance: float,
        novelty: object,
        trend_velocity: float,
        entity_names: list[str],
        cluster_id: int,
        pending_news_id: int | None,
        event_type: str,
        is_new: bool,
    ) -> None:
        from bot.editorial.novelty import NoveltyBreakdown

        assert isinstance(novelty, NoveltyBreakdown)
        self._repo.update_metrics(
            story_id,
            importance_score=importance,
            novelty_score=novelty.novelty_score,
            trend_velocity=trend_velocity,
            redundancy_score=novelty.redundancy_score,
            update_delta_score=novelty.update_delta_score,
        )
        self._repo.upsert_entities(story_id, entity_names)
        self._graph.record_entities(entity_names, story_id=story_id)
        self._repo.link_cluster(
            story_id=story_id,
            cluster_id=cluster_id,
            pending_news_id=pending_news_id,
        )

        from bot.observability.metrics import (
            observe_importance_score,
            record_story_escalation,
            record_story_update,
            refresh_story_gauges,
        )

        record_story_update(created=is_new)
        if is_escalation(event_type):
            record_story_escalation()
        observe_importance_score(importance)
        refresh_story_gauges(self._repo.count_active())
        if self._federation is not None:
            vec = self._federation.get_version(story_id)
            self._federation.commit_update(
                story_id=story_id,
                expected_version=vec.version if vec else None,
                payload={
                    "importance": importance,
                    "event_type": event_type,
                    "cluster_id": cluster_id,
                },
            )

    def maintenance_pass(self) -> int:
        archived = self._repo.archive_stale_stories()
        from bot.observability.metrics import refresh_story_gauges

        refresh_story_gauges(self._repo.count_active())
        return archived


def _hours_since(iso_ts: str) -> float:
    try:
        then = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - then).total_seconds() / 3600.0)
    except ValueError:
        return 0.0


def _merge_languages(existing_json: str | None, new_langs: list[str]) -> list[str]:
    merged = set(new_langs)
    if existing_json:
        try:
            parsed = json.loads(existing_json)
            if isinstance(parsed, list):
                merged.update(str(code) for code in parsed)
        except json.JSONDecodeError:
            pass
    return sorted(merged)
