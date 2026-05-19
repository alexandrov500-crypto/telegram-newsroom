from __future__ import annotations

import os
import time


class RecoveryCooldown:
    """Limit recovery hooks to at most one action per subsystem per interval."""

    def __init__(self, min_interval_sec: float | None = None) -> None:
        self._min = min_interval_sec or float(
            os.getenv("RUNTIME_RECOVERY_COOLDOWN_SEC", "60"),
        )
        self._last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        if now - last < self._min:
            return False
        self._last[key] = now
        return True

    def remaining(self, key: str) -> float:
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        return max(0.0, self._min - (now - last))
