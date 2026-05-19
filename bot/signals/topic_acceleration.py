from __future__ import annotations

from bot.storage.signal_repository import SignalRepository


def topic_key_from_tags(tags: list[str]) -> str:
    if not tags:
        return "general"
    return tags[0].lower().strip()[:40]


class TopicAcceleration:
    """Detect abnormal topic frequency acceleration."""

    def __init__(self, repository: SignalRepository) -> None:
        self._repo = repository

    def record_and_score(
        self,
        *,
        topic: str,
        cluster_variants: int,
        source_count: int,
    ) -> tuple[float, float]:
        """
        Returns (acceleration_score, z_score) for topic activity.
        """
        activity = float(cluster_variants) + source_count * 0.5
        _, _, z = self._repo.update_baseline(
            scope="topic",
            scope_key=topic,
            metric="activity",
            observed=activity,
        )
        acceleration = min(1.0, max(0.0, (z - 1.0) / 3.0)) if z > 1.0 else 0.0
        return acceleration, z
