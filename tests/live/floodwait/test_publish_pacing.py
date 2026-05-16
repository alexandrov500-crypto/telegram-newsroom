"""Publish pacing and burst limits (deterministic clock)."""

from __future__ import annotations

import asyncio
import time

from publisher.rate_limit import ChannelPublishRateLimiter, reset_publish_rate_limiter_for_tests


def test_burst_cap_delays_third_message_in_window() -> None:
    reset_publish_rate_limiter_for_tests()
    t = {"now": 0.0}

    def clock() -> float:
        return t["now"]

    async def fake_sleep(sec: float) -> None:
        t["now"] += sec

    lim = ChannelPublishRateLimiter(
        min_interval_sec=0.0,
        burst_window_sec=10.0,
        burst_max_messages=2,
        clock=clock,
    )

    async def body() -> None:
        import publisher.rate_limit as rl

        original = rl.asyncio.sleep
        rl.asyncio.sleep = fake_sleep
        try:
            await lim.acquire_before_publish(1)
            await lim.acquire_before_publish(1)
            t["now"] = 5.0
            await lim.acquire_before_publish(1)
            assert t["now"] >= 10.0
        finally:
            rl.asyncio.sleep = original

    asyncio.run(body())


def test_min_interval_enforced() -> None:
    t = {"now": 100.0}

    def clock() -> float:
        return t["now"]

    async def fake_sleep(sec: float) -> None:
        t["now"] += sec

    lim = ChannelPublishRateLimiter(
        min_interval_sec=2.0,
        burst_window_sec=60.0,
        burst_max_messages=10,
        clock=clock,
    )

    async def body() -> None:
        import publisher.rate_limit as rl

        original = rl.asyncio.sleep
        rl.asyncio.sleep = fake_sleep
        try:
            await lim.acquire_before_publish(99)
            t["now"] = 100.5
            await lim.acquire_before_publish(99)
            assert t["now"] >= 102.0
        finally:
            rl.asyncio.sleep = original

    asyncio.run(body())
