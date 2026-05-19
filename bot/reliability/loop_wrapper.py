from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Awaitable, Callable, TypeVar

from bot.observability.loop_registry import get_loop_registry
from bot.reliability.context import bind_log_context
from bot.reliability.types import SubsystemName

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def reliability_loop(
    name: str,
    interval_sec: float,
    *,
    subsystem: SubsystemName | None = None,
) -> Callable[[F], F]:
    """Register heartbeat + structured context on background coroutine loops."""

    def decorator(fn: F) -> F:
        from bot.runtime.profile import is_loop_enabled_in_profile

        reg = get_loop_registry()
        if is_loop_enabled_in_profile(name):
            reg.register(name, interval_sec)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            sub = subsystem or SubsystemName.SCHEDULER
            while True:
                started = time.perf_counter()
                err: str | None = None
                with bind_log_context(subsystem=sub.value, loop=name):
                    try:
                        await fn(*args, **kwargs)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        err = str(exc)[:200]
                        raise
                    finally:
                        reg.heartbeat(name, time.perf_counter() - started, error=err)
                if False:
                    break
                await asyncio.sleep(interval_sec)

        return wrapper  # type: ignore[return-value]

    return decorator
