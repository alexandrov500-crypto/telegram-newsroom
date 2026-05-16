from __future__ import annotations

import asyncio

from publisher.rate_limit import ChannelPublishRateLimiter


def test_burst_limiter_waits(monkeypatch) -> None:
    t = [0.0]

    def clock() -> float:
        return t[0]

    async def fake_sleep(dt: float) -> None:
        t[0] += float(dt)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    lim = ChannelPublishRateLimiter(
        min_interval_sec=0.0,
        burst_window_sec=1.0,
        burst_max_messages=2,
        clock=clock,
    )

    async def body() -> None:
        await lim.acquire_before_publish(42)
        t[0] = 0.05
        await lim.acquire_before_publish(42)
        t[0] = 0.06
        await lim.acquire_before_publish(42)

    asyncio.run(body())
    assert t[0] >= 0.9
