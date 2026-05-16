"""Distributed or local lock around a draft publish (multi-worker safety)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

_local_locks: dict[int, asyncio.Lock] = {}
_local_locks_guard = asyncio.Lock()


@asynccontextmanager
async def publish_draft_lock(
    settings: Any,
    draft_id: int,
    *,
    ttl_sec: int = 180,
) -> AsyncIterator[bool]:
    """
    Yields True if lock acquired, False if contended (caller should treat as already_handled).
    Redis: SET NX EX. Local: per-draft asyncio.Lock.
    """
    from utils.redis_client import get_redis

    strict = bool(getattr(settings, "publish_lock_strict", False))
    r = await get_redis()
    if r is None:
        if strict and bool(getattr(settings, "redis_enabled", False)):
            from utils.reliability_diagnostics import record_lock_event

            record_lock_event(
                draft_id=draft_id,
                event="strict_denied",
                strict=True,
                redis_available=False,
                detail="redis_unavailable_strict_mode",
            )
            yield False
            return
        lock = await _get_local_lock(draft_id)
        await lock.acquire()
        try:
            yield True
        finally:
            lock.release()
    else:
        prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom").rstrip(":")
        key = f"{prefix}:publish_lock:{draft_id}"
        try:
            ok = await r.set(key, "1", nx=True, ex=max(10, min(ttl_sec, 3600)))
            if not ok:
                from utils.reliability_diagnostics import record_lock_event

                record_lock_event(
                    draft_id=draft_id,
                    event="contention",
                    strict=strict,
                    redis_available=True,
                    detail="set_nx_failed",
                )
                yield False
            else:
                try:
                    yield True
                finally:
                    try:
                        await r.delete(key)
                    except Exception as exc:
                        logger.warning(
                            "publish_lock.redis_release_failed draft_id=%s error=%s",
                            draft_id,
                            repr(exc),
                        )
        except Exception as exc:
            from utils.reliability_diagnostics import record_lock_event

            if strict:
                record_lock_event(
                    draft_id=draft_id,
                    event="strict_denied",
                    strict=True,
                    redis_available=False,
                    detail=repr(exc),
                )
                logger.warning(
                    "publish_lock.strict_denied draft_id=%s error=%s",
                    draft_id,
                    repr(exc),
                )
                yield False
                return
            record_lock_event(
                draft_id=draft_id,
                event="redis_fallback",
                strict=False,
                redis_available=False,
                detail=repr(exc),
            )
            logger.warning("publish_lock.redis_failed draft_id=%s error=%s fallback=local", draft_id, repr(exc))
            lock = await _get_local_lock(draft_id)
            await lock.acquire()
            try:
                yield True
            finally:
                lock.release()


async def _get_local_lock(draft_id: int) -> asyncio.Lock:
    async with _local_locks_guard:
        lk = _local_locks.get(draft_id)
        if lk is None:
            lk = asyncio.Lock()
            _local_locks[draft_id] = lk
        return lk


def reset_publish_locks_for_tests() -> None:
    _local_locks.clear()
