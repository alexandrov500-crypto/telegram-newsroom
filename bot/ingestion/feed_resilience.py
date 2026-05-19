from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from bot.operations.repository import OperationsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedResilienceVerdict:
    allowed: bool
    quarantined: bool
    reason: str
    reliability: float


class FeedResilienceLayer:
    """Quarantine noisy feeds, suppress duplicate bursts, track malformation."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository
        self._burst_window: dict[str, list[float]] = {}
        self._burst_threshold = 40
        self._burst_window_sec = 300.0

    def evaluate_feed(self, feed_url: str, *, source_name: str) -> FeedResilienceVerdict:
        if self._repo.is_feed_quarantined(feed_url):
            return FeedResilienceVerdict(
                allowed=False,
                quarantined=True,
                reason="quarantined",
                reliability=0.0,
            )
        health = self._repo.get_feed_health(feed_url)
        reliability = float(health.get("reliability_score", 0.8)) if health else 0.8
        if reliability < 0.25:
            self._repo.quarantine_feed(feed_url, source_name=source_name, reason="low_reliability")
            try:
                from bot.observability.metrics import record_feed_quarantine

                record_feed_quarantine()
            except Exception:
                pass
            return FeedResilienceVerdict(
                allowed=False,
                quarantined=True,
                reason="low_reliability",
                reliability=reliability,
            )
        return FeedResilienceVerdict(
            allowed=True,
            quarantined=False,
            reason="ok",
            reliability=reliability,
        )

    def record_malformed(self, feed_url: str, *, source_name: str) -> None:
        try:
            from bot.observability.metrics import record_malformed_feed_event

            record_malformed_feed_event()
        except Exception:
            pass
        self._repo.increment_feed_malformed(feed_url, source_name=source_name)

    def record_duplicate_burst(self, feed_url: str) -> bool:
        """Returns True if burst was suppressed."""
        now = time.monotonic()
        window = self._burst_window.setdefault(feed_url, [])
        window[:] = [t for t in window if now - t < self._burst_window_sec]
        window.append(now)
        if len(window) > self._burst_threshold:
            try:
                from bot.observability.metrics import record_duplicate_burst_suppressed

                record_duplicate_burst_suppressed()
            except Exception:
                pass
            return True
        return False
