from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.reliability.types import RuntimeHealthSnapshot


@dataclass(frozen=True)
class AggregatedMetrics:
    stories_processed: int
    publish_candidates: int
    publish_success_rate: float
    token_usd: float
    cognition_latency_ms: float
    open_incidents: int
    top_sources: tuple[tuple[str, int], ...]
    retry_count: int
    failure_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "stories_processed": self.stories_processed,
            "publish_candidates": self.publish_candidates,
            "publish_success_rate": round(self.publish_success_rate, 4),
            "token_usd": round(self.token_usd, 4),
            "cognition_latency_ms": round(self.cognition_latency_ms, 1),
            "open_incidents": self.open_incidents,
            "top_sources": list(self.top_sources),
            "retry_count": self.retry_count,
            "failure_count": self.failure_count,
        }


class MetricsAggregator:
    """Roll up DB + health snapshot into operator-facing metrics."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def aggregate(self, *, health: RuntimeHealthSnapshot | None = None) -> AggregatedMetrics:
        counts = self._repo.table_row_counts()
        pending = int(counts.get("pending_news", 0))
        published = int(counts.get("published_news", 0)) if "published_news" in counts else 0
        failures = int(counts.get("rejected_drafts", 0)) if "rejected_drafts" in counts else 0
        open_i = len(self._repo.list_incidents(status="open", limit=100))

        token_usd = 0.0
        success_rate = 1.0
        try:
            success_rate = float(self._repo.telegram_delivery_success_rate(hours=24))
        except Exception:
            pass

        cog_ms = 0.0
        if health is not None:
            for s in health.subsystems:
                if s.name.value == "cognition":
                    cog_ms = float(s.metadata.get("latency_ms", 0))

        top: list[tuple[str, int]] = []
        try:
            for row in self._repo.feed_health_report(limit=5):
                top.append(
                    (str(row.get("source_name", "?")), int(row.get("items_fetched", 0))),
                )
        except Exception:
            pass

        retries = health.retries_per_hour if health else 0
        return AggregatedMetrics(
            stories_processed=pending + published,
            publish_candidates=pending,
            publish_success_rate=success_rate,
            token_usd=token_usd,
            cognition_latency_ms=cog_ms,
            open_incidents=open_i,
            top_sources=tuple(top),
            retry_count=retries,
            failure_count=failures,
        )
