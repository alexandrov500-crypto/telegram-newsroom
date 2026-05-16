from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from utils.metrics import inc

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def async_retry(
    op: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    delay_sec: float = 0.6,
    label: str = "op",
) -> T:
    last: BaseException | None = None
    for i in range(1, attempts + 1):
        try:
            return await op()
        except BaseException as exc:
            last = exc
            if i >= attempts:
                raise
            inc("publish_retries")
            logger.warning("%s retry %s/%s: %s", label, i, attempts, repr(exc))
            await asyncio.sleep(delay_sec)
    assert last is not None
    raise last
