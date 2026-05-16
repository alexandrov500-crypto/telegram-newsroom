from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Callable


class ChannelPublishRateLimiter:
    """
    In-process per-channel publish spacing + burst cap (no Redis).
    ``clock`` injectable for deterministic tests.
    """

    def __init__(
        self,
        *,
        min_interval_sec: float,
        burst_window_sec: float,
        burst_max_messages: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = max(0.0, float(min_interval_sec))
        self._burst_window = max(1.0, float(burst_window_sec))
        self._burst_max = max(1, int(burst_max_messages))
        self._clock = clock
        self._last_start: dict[int, float] = {}
        self._starts: dict[int, deque[float]] = {}

    async def acquire_before_publish(self, channel_id: int) -> None:
        cid = int(channel_id)
        now = self._clock()
        last = self._last_start.get(cid)
        if last is not None and self._min_interval > 0:
            wait = self._min_interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
                now = self._clock()

        dq = self._starts.setdefault(cid, deque())
        while dq and now - dq[0] > self._burst_window:
            dq.popleft()
        if len(dq) >= self._burst_max:
            wait2 = self._burst_window - (now - dq[0])
            if wait2 > 0:
                await asyncio.sleep(wait2)
                now = self._clock()
                while dq and now - dq[0] > self._burst_window:
                    dq.popleft()

        dq.append(now)
        self._last_start[cid] = now


_limiter: ChannelPublishRateLimiter | None = None
_limiter_key: tuple[float, float, int] | None = None


def get_publish_rate_limiter(
    *,
    min_interval_sec: float,
    burst_window_sec: float,
    burst_max_messages: int,
    clock: Callable[[], float] | None = None,
) -> ChannelPublishRateLimiter:
    global _limiter, _limiter_key
    ck = clock or time.monotonic
    key = (float(min_interval_sec), float(burst_window_sec), int(burst_max_messages), id(ck))
    if _limiter is None or _limiter_key != key:
        _limiter = ChannelPublishRateLimiter(
            min_interval_sec=key[0],
            burst_window_sec=key[1],
            burst_max_messages=key[2],
            clock=ck,
        )
        _limiter_key = key
    return _limiter


def reset_publish_rate_limiter_for_tests() -> None:
    global _limiter, _limiter_key
    _limiter = None
    _limiter_key = None
