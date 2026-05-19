from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


@dataclass
class ObservabilityRegistry:
    """Mutable operational probes (single instance injected at startup)."""

    scheduler_running: bool = False
    rss_ingestion_running: bool = False
    telegram_ingestion_running: bool = False
    digest_scheduler_running: bool = False
    analytics_scheduler_running: bool = False
    telegram_connected: bool = False
    openai_available: bool = False
    watchdog_restarts: int = 0
    last_rss_cycle_at: datetime | None = None
    last_telegram_cycle_at: datetime | None = None
    last_event_loop_probe_at: datetime | None = None
    event_loop_lag_sec: float = 0.0
    _queue_backlog_fn: Callable[[], int] | None = field(default=None, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def set_queue_backlog_provider(self, provider: Callable[[], int]) -> None:
        self._queue_backlog_fn = provider

    async def mark_rss_cycle(self) -> None:
        async with self._lock:
            self.last_rss_cycle_at = datetime.now(timezone.utc)
            self.rss_ingestion_running = True

    async def mark_telegram_cycle(self, *, connected: bool) -> None:
        async with self._lock:
            self.last_telegram_cycle_at = datetime.now(timezone.utc)
            self.telegram_ingestion_running = True
            self.telegram_connected = connected

    async def mark_event_loop_probe(self, lag_sec: float) -> None:
        async with self._lock:
            self.last_event_loop_probe_at = datetime.now(timezone.utc)
            self.event_loop_lag_sec = lag_sec

    def queue_backlog(self) -> int:
        if self._queue_backlog_fn is None:
            return 0
        try:
            return int(self._queue_backlog_fn())
        except Exception:
            return 0

    async def snapshot(self) -> dict[str, object]:
        async with self._lock:
            return {
                "scheduler": "running" if self.scheduler_running else "stopped",
                "rss_ingestion": self.rss_ingestion_running,
                "telegram_ingestion": self.telegram_ingestion_running,
                "telegram": "connected" if self.telegram_connected else "disconnected",
                "openai": "available" if self.openai_available else "unavailable",
                "queue_backlog": self.queue_backlog(),
                "event_loop_lag_sec": round(self.event_loop_lag_sec, 4),
                "watchdog_restarts": self.watchdog_restarts,
                "last_rss_cycle_at": (
                    self.last_rss_cycle_at.isoformat() if self.last_rss_cycle_at else None
                ),
                "last_telegram_cycle_at": (
                    self.last_telegram_cycle_at.isoformat()
                    if self.last_telegram_cycle_at
                    else None
                ),
            }
