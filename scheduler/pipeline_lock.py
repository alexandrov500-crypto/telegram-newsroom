from __future__ import annotations

import asyncio
import threading

_init_lock = threading.Lock()
_async_lock: asyncio.Lock | None = None


def get_pipeline_lock() -> asyncio.Lock:
    """
    Process-wide singleton asyncio.Lock for the newsroom pipeline.
    Thread-safe lazy init (safe if multiple coroutines call on first tick).
    """
    global _async_lock
    with _init_lock:
        if _async_lock is None:
            _async_lock = asyncio.Lock()
        return _async_lock
