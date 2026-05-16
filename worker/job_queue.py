"""Internal async job queue: Redis-backed or in-memory fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class JobKind(str, Enum):
    INGEST = "ingest"
    AI = "ai"
    PUBLISHER = "publisher"


@dataclass(slots=True)
class JobRetryMeta:
    attempt: int = 0
    max_attempts: int = 5
    backoff_sec: float = 1.0


@dataclass(slots=True)
class JobEnvelope:
    kind: JobKind
    payload: dict[str, Any]
    retry: JobRetryMeta = field(default_factory=JobRetryMeta)

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind.value,
                "payload": self.payload,
                "retry": asdict(self.retry),
            },
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def from_json(raw: str) -> JobEnvelope:
        d = json.loads(raw)
        r = d.get("retry") or {}
        return JobEnvelope(
            kind=JobKind(d["kind"]),
            payload=dict(d.get("payload") or {}),
            retry=JobRetryMeta(
                attempt=int(r.get("attempt", 0)),
                max_attempts=int(r.get("max_attempts", 5)),
                backoff_sec=float(r.get("backoff_sec", 1.0)),
            ),
        )


class JobQueue(Protocol):
    async def enqueue(self, job: JobEnvelope) -> None: ...

    async def dequeue(self, kind: JobKind, *, timeout_sec: float) -> JobEnvelope | None: ...

    async def depth(self, kind: JobKind) -> int: ...

    async def ack(self, job: JobEnvelope) -> None: ...

    async def aclose(self) -> None: ...


class InMemoryJobQueue:
    """Per-process FIFO queues (development / degraded mode)."""

    def __init__(self) -> None:
        self._queues: dict[JobKind, asyncio.Queue[JobEnvelope]] = {k: asyncio.Queue() for k in JobKind}

    async def enqueue(self, job: JobEnvelope) -> None:
        await self._queues[job.kind].put(job)

    async def dequeue(self, kind: JobKind, *, timeout_sec: float) -> JobEnvelope | None:
        try:
            return await asyncio.wait_for(self._queues[kind].get(), timeout=max(0.001, timeout_sec))
        except asyncio.TimeoutError:
            return None

    async def depth(self, kind: JobKind) -> int:
        return self._queues[kind].qsize()

    async def ack(self, job: JobEnvelope) -> None:
        return None

    async def aclose(self) -> None:
        return None


class RedisJobQueue:
    """LPUSH / BRPOP lists under NEWSROOM_QUEUE_PREFIX."""

    def __init__(self, redis_client: Any, *, prefix: str) -> None:
        self._r = redis_client
        self._prefix = prefix.rstrip(":")

    def _key(self, kind: JobKind) -> str:
        return f"{self._prefix}:jobq:{kind.value}"

    async def enqueue(self, job: JobEnvelope) -> None:
        await self._r.lpush(self._key(job.kind), job.to_json())

    async def dequeue(self, kind: JobKind, *, timeout_sec: float) -> JobEnvelope | None:
        t = max(0, int(math.ceil(timeout_sec)))
        if t == 0:
            t = 1
        res = await self._r.brpop(self._key(kind), timeout=t)
        if res is None:
            return None
        _, raw = res
        return JobEnvelope.from_json(raw)

    async def depth(self, kind: JobKind) -> int:
        n = await self._r.llen(self._key(kind))
        return int(n or 0)

    async def ack(self, job: JobEnvelope) -> None:
        return None

    async def aclose(self) -> None:
        return None


_queue: JobQueue | None = None


def reset_job_queue_for_tests() -> None:
    global _queue
    _queue = None


def build_job_queue(settings: Any, redis_client: Any | None) -> JobQueue:
    prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom")
    if bool(getattr(settings, "redis_enabled", False)) and redis_client is not None:
        return RedisJobQueue(redis_client, prefix=prefix)
    return InMemoryJobQueue()


def get_job_queue() -> JobQueue:
    if _queue is None:
        raise RuntimeError("Job queue not initialized; call init_job_queue first")
    return _queue


async def init_job_queue(settings: Any) -> None:
    global _queue
    if _queue is not None:
        return
    from utils.redis_client import get_redis

    r = await get_redis()
    _queue = build_job_queue(settings, r)
    mode = "redis" if isinstance(_queue, RedisJobQueue) else "memory"
    logger.info("job_queue.initialized mode=%s", mode)


async def close_job_queue() -> None:
    global _queue
    if _queue is None:
        return
    try:
        await _queue.aclose()
    finally:
        _queue = None
        logger.info("job_queue.closed")
