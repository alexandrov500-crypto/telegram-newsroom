"""Test doubles for Redis clients (lightweight failure injection)."""

from __future__ import annotations

from typing import Any


class BrpoplpushFailProxy:
    """Wrap a redis.asyncio client; first N ``brpoplpush`` calls raise ``ConnectionError``."""

    def __init__(self, inner: Any, *, fail_brpoplpush: int = 0) -> None:
        self._inner = inner
        self._br_left = int(fail_brpoplpush)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name != "brpoplpush":
            return attr

        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if self._br_left > 0:
                self._br_left -= 1
                raise ConnectionError("simulated_network_partition")
            return await self._inner.brpoplpush(*args, **kwargs)

        return _wrapped
