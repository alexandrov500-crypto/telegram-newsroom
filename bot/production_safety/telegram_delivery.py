from __future__ import annotations

import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field

from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.types import TelegramDeliveryStats

logger = logging.getLogger(__name__)


@dataclass
class TelegramDeliveryGuard:
    """FloodWait-aware pacing, duplicate prevention hooks, emergency pause."""

    settings: ProductionSafetySettings
    _last_send_monotonic: float = 0.0
    _floodwait_events: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    _failures: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    _latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    publish_paused: bool = False
    operator_override: bool = False
    _channel_last_send: dict[int, float] = field(default_factory=dict)

    def pause_publish(self, *, reason: str) -> None:
        self.publish_paused = True
        logger.warning("event=telegram_publish_paused reason=%s", reason)

    def resume_publish(self) -> None:
        self.publish_paused = False
        self.operator_override = True
        logger.info("event=telegram_publish_resumed operator_override=true")

    def record_floodwait(self, retry_after_sec: float) -> float:
        now = time.monotonic()
        self._floodwait_events.append(now)
        backoff = retry_after_sec * self.settings.floodwait_backoff_multiplier
        backoff += random.uniform(0.1, 0.8)
        try:
            from bot.observability.metrics import record_telegram_floodwait

            record_telegram_floodwait()
        except Exception:
            pass
        logger.warning("event=telegram_floodwait backoff_sec=%.1f", backoff)
        return backoff

    def record_delivery(
        self,
        *,
        success: bool,
        latency_ms: float,
        channel_id: int | None = None,
    ) -> None:
        now = time.monotonic()
        if success:
            self._latencies_ms.append(latency_ms)
        else:
            self._failures.append(now)
        if channel_id is not None:
            self._channel_last_send[channel_id] = now

    async def await_send_slot(self, channel_id: int | None = None) -> bool:
        """Rate-shape before Telegram API calls. Returns False if publish blocked."""
        if self.publish_paused and not self.operator_override:
            return False
        now = time.monotonic()
        min_gap = self.settings.telegram_min_interval_sec
        if self._floodwait_events and now - self._floodwait_events[-1] < 30:
            min_gap *= 2.0
        since = now - self._last_send_monotonic
        if since < min_gap:
            import asyncio

            await asyncio.sleep(min_gap - since + random.uniform(0, 0.15))
        if channel_id is not None:
            ch_last = self._channel_last_send.get(channel_id, 0.0)
            ch_gap = now - ch_last
            if ch_gap < min_gap:
                import asyncio

                await asyncio.sleep(min_gap - ch_gap)
        self._last_send_monotonic = time.monotonic()
        return True

    def stats(self) -> TelegramDeliveryStats:
        now = time.monotonic()
        hour = 3600.0
        fw = sum(1 for t in self._floodwait_events if now - t < hour)
        fail = sum(1 for t in self._failures if now - t < hour)
        total = fw + fail + max(len(self._latencies_ms), 1)
        success_ratio = 1.0 - (fail / total)
        avg_lat = (
            sum(self._latencies_ms) / len(self._latencies_ms) if self._latencies_ms else 0.0
        )
        return TelegramDeliveryStats(
            latency_ms_avg=avg_lat,
            floodwait_count_hour=fw,
            failure_count_hour=fail,
            success_ratio=max(0.0, min(1.0, success_ratio)),
            publish_paused=self.publish_paused,
            operator_override=self.operator_override,
        )
