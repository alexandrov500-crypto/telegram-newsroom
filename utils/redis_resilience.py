"""Bounded exponential backoff + jitter for transient Redis failures (worker transport)."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

try:
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError
except Exception:  # pragma: no cover - redis optional in some contexts
    RedisConnectionError = ConnectionError  # type: ignore[misc,assignment]
    RedisTimeoutError = TimeoutError  # type: ignore[misc,assignment]


def redis_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (RedisConnectionError, RedisTimeoutError, OSError, TimeoutError, asyncio.TimeoutError)):
        return True
    name = type(exc).__name__
    if name in {"ConnectionResetError", "BrokenPipeError", "ConnectionAbortedError"}:
        return True
    return False


def _retry_budget(settings: Any | None) -> tuple[int, float, float]:
    max_retries = int(getattr(settings, "redis_transport_max_retries", 5) or 5)
    base = float(getattr(settings, "redis_transport_backoff_sec", 0.25) or 0.25)
    cap = float(getattr(settings, "redis_transport_backoff_max_sec", 8.0) or 8.0)
    max_retries = max(1, min(max_retries, 30))
    base = max(0.05, min(base, 30.0))
    cap = max(base, min(cap, 120.0))
    return max_retries, base, cap


async def redis_call_with_retry(
    factory: Callable[[], Awaitable[T]],
    settings: Any | None,
    op_name: str,
    *,
    extra_log: dict[str, Any] | None = None,
) -> T:
    """
    Run an async Redis operation with retries on transient connection errors.
    On success after at least one retry, emits a structured recovery log line.
    """
    max_retries, base, cap = _retry_budget(settings)
    last: BaseException | None = None
    extra = dict(extra_log or {})
    for attempt in range(max_retries):
        try:
            out = await factory()
            if attempt > 0:
                try:
                    from utils.redis_transport_metrics import record_transport_op_recovered

                    record_transport_op_recovered()
                except Exception:
                    pass
                logger.info(
                    "redis.transport_recovered op=%s attempts=%s",
                    op_name,
                    attempt + 1,
                    extra={**extra, "op": op_name, "attempts": attempt + 1},
                )
            return out
        except BaseException as exc:
            last = exc
            if not redis_transient_error(exc) or attempt >= max_retries - 1:
                raise
            exp = min(cap, base * (2**attempt))
            jitter = random.uniform(0.0, max(0.0, exp * 0.25))
            delay = min(cap, exp + jitter)
            try:
                from utils.redis_transport_metrics import record_transport_op_retry_event

                record_transport_op_retry_event()
            except Exception:
                pass
            logger.warning(
                "redis.transport_retry op=%s attempt=%s/%s sleep_sec=%.3f error=%s",
                op_name,
                attempt + 1,
                max_retries,
                delay,
                repr(exc),
                extra={**extra, "op": op_name, "attempt": attempt + 1, "max_retries": max_retries},
            )
            await asyncio.sleep(delay)
    assert last is not None
    raise last


def monotonic_backoff_sleep_sec(attempt: int, settings: Any | None) -> float:
    """Used by outer loops (e.g. dequeue) when inner retries are exhausted."""
    _, base, cap = _retry_budget(settings)
    exp = min(cap, base * (2 ** max(0, attempt)))
    jitter = random.uniform(0.0, max(0.0, exp * 0.2))
    return min(cap, exp + jitter)
