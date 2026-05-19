from __future__ import annotations

from bot.editorial.story_types import StorySnapshot
from bot.storage.story_repository import StoryRepository, StoryTimelineEntry


class StoryRegistry:
    """Abstract-friendly facade over story persistence."""

    def __init__(self, repository: StoryRepository) -> None:
        self._repo = repository

    @property
    def repository(self) -> StoryRepository:
        return self._repo

    def get(self, story_id: int) -> StorySnapshot | None:
        return self._repo.get_story(story_id)

    def active_stories(self, *, limit: int = 80) -> list[StorySnapshot]:
        return self._repo.list_active_stories(limit=limit)

    def trending(self, *, limit: int = 10) -> list[StorySnapshot]:
        return self._repo.list_trending(limit=limit)

    def top_stories(self, *, limit: int = 10) -> list[StorySnapshot]:
        return self._repo.list_top_by_importance(limit=limit)

    def timeline(self, story_id: int, *, limit: int = 12) -> list[StoryTimelineEntry]:
        return self._repo.timeline(story_id, limit=limit)

    def story_for_cluster(self, cluster_id: int) -> StorySnapshot | None:
        story_id = self._repo.story_id_for_cluster(cluster_id)
        if story_id is None:
            return None
        return self._repo.get_story(story_id)

    def entity_map(self, stories: list[StorySnapshot]) -> dict[int, set[str]]:
        ids = [story.id for story in stories]
        return self._repo.entity_map_for_stories(ids)

    def lifecycle_counts(self) -> dict[str, int]:
        return self._repo.count_by_status()

    def archive_stale(self) -> int:
        return self._repo.archive_stale_stories()
