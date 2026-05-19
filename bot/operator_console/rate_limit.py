from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Per-category cooldown for Telegram operator notifications."""

    default_cooldown_sec: float = 60.0
    _last: dict[str, float] = field(default_factory=dict)
    _burst: dict[str, int] = field(default_factory=dict)
    _burst_window_start: dict[str, float] = field(default_factory=dict)

    def allow(
        self,
        category: str,
        *,
        cooldown_sec: float | None = None,
        max_burst: int = 5,
        burst_window_sec: float = 120.0,
    ) -> bool:
        now = time.monotonic()
        cd = cooldown_sec if cooldown_sec is not None else self.default_cooldown_sec
        last = self._last.get(category)
        if last is not None and (now - last) < cd:
            return False
        win_start = self._burst_window_start.get(category, now)
        if now - win_start > burst_window_sec:
            self._burst_window_start[category] = now
            self._burst[category] = 0
        count = self._burst.get(category, 0) + 1
        if count > max_burst:
            return False
        self._burst[category] = count
        self._last[category] = now
        return True

    def reset(self, category: str) -> None:
        self._last.pop(category, None)
        self._burst.pop(category, None)
        self._burst_window_start.pop(category, None)
