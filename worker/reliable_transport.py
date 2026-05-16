from __future__ import annotations

"""
Reliable at-least-once job transport (Redis lists + inflight markers, or in-memory).

Redis: BRPOPLPUSH pending→processing, SETEX inflight:{delivery_id},
recovery when inflight key expired (TTL = visibility). ACK: LREM processing + DEL inflight.

In-memory: leased map + deadline; same semantics without Redis.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import replace
from typing import Any, Protocol

from worker.dlq_record import build_dlq_record
from worker.job_queue import JobEnvelope, JobKind

logger = logging.getLogger(__name__)


class ReliableJobTransport(Protocol):
    async def enqueue(self, job: JobEnvelope) -> None: ...

    async def lease_dequeue(
        self,
        kind: JobKind,
        *,
        shutdown: asyncio.Event,
        visibility_sec: int,
        poll_timeout_sec: float = 1.0,
    ) -> tuple[str, JobEnvelope] | None: ...

    async def ack(self, kind: JobKind, raw_exact: str, *, delivery_id: str) -> None: ...

    async def nack_requeue(self, kind: JobKind, raw_exact: str, *, delivery_id: str) -> None: ...

    async def nack_dlq(
        self,
        kind: JobKind,
        raw_exact: str,
        *,
        delivery_id: str,
        reason: str,
        dlq_meta: dict[str, Any] | None = None,
    ) -> None: ...

    async def recover_stale(self, kind: JobKind, *, visibility_sec: int) -> int: ...

    async def depth_pending(self, kind: JobKind) -> int: ...

    async def depth_processing(self, kind: JobKind) -> int: ...

    async def list_dlq(self, kind: JobKind, *, limit: int = 50) -> list[dict[str, Any]]: ...

    async def replay_dlq_index(self, kind: JobKind, *, index: int) -> bool: ...

    async def aclose(self) -> None: ...


def _ensure_delivery_id(job: JobEnvelope) -> tuple[JobEnvelope, str]:
    payload = dict(job.payload)
    did = str(payload.get("delivery_id") or "").strip() or str(uuid.uuid4())
    payload["delivery_id"] = did
    if "_enqueue_wall_ts" not in payload:
        payload["_enqueue_wall_ts"] = time.time()
    return replace(job, payload=payload), did


class InMemoryReliableTransport:
    """Single-process leased dequeue; visibility in-process only (crash = possible loss)."""

    def __init__(self) -> None:
        self._pending: dict[JobKind, asyncio.Queue[str]] = {k: asyncio.Queue() for k in JobKind}
        self._leased: dict[str, tuple[JobKind, str, float]] = {}
        self._lock = asyncio.Lock()
        self._dlq: dict[JobKind, list[str]] = {k: [] for k in JobKind}

    async def enqueue(self, job: JobEnvelope) -> None:
        j2, _ = _ensure_delivery_id(job)
        raw = j2.to_json()
        await self._pending[job.kind].put(raw)

    async def lease_dequeue(
        self,
        kind: JobKind,
        *,
        shutdown: asyncio.Event,
        visibility_sec: int,
        poll_timeout_sec: float = 1.0,
    ) -> tuple[str, JobEnvelope] | None:
        while not shutdown.is_set():
            try:
                raw = await asyncio.wait_for(
                    self._pending[kind].get(),
                    timeout=min(max(0.05, poll_timeout_sec), 1.0),
                )
            except asyncio.TimeoutError:
                continue
            j2, did = _ensure_delivery_id(JobEnvelope.from_json(raw))
            raw_final = j2.to_json()
            deadline = time.monotonic() + max(0.05, float(visibility_sec))
            async with self._lock:
                self._leased[did] = (kind, raw_final, deadline)
            return raw_final, j2
        return None

    async def ack(self, kind: JobKind, raw_exact: str, *, delivery_id: str) -> None:
        async with self._lock:
            self._leased.pop(delivery_id, None)

    async def nack_requeue(self, kind: JobKind, raw_exact: str, *, delivery_id: str) -> None:
        async with self._lock:
            self._leased.pop(delivery_id, None)
        await self._pending[kind].put(raw_exact)

    async def nack_dlq(
        self,
        kind: JobKind,
        raw_exact: str,
        *,
        delivery_id: str,
        reason: str,
        dlq_meta: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            self._leased.pop(delivery_id, None)
        record = build_dlq_record(
            kind=kind.value,
            delivery_id=delivery_id,
            reason=reason,
            original=raw_exact,
            dlq_meta=dlq_meta,
        )
        blob = json.dumps(record, default=str)
        self._dlq[kind].insert(0, blob)
        logger.warning(
            "job.dlq kind=%s delivery_id=%s reason=%s",
            kind.value,
            delivery_id,
            reason[:200],
            extra={"dlq_terminal": (dlq_meta or {}).get("terminal"), "failure_class": (dlq_meta or {}).get("failure_class")},
        )

    async def recover_stale(self, kind: JobKind, *, visibility_sec: int) -> int:
        now = time.monotonic()
        moved = 0
        async with self._lock:
            for did, (k, raw, deadline) in list(self._leased.items()):
                if k != kind:
                    continue
                if now > deadline:
                    self._leased.pop(did, None)
                    await self._pending[kind].put(raw)
                    moved += 1
        return moved

    async def count_recoverable_stale(self, kind: JobKind, *, visibility_sec: int) -> int:
        _ = visibility_sec
        now = time.monotonic()
        n = 0
        async with self._lock:
            for _did, (k, _raw, deadline) in self._leased.items():
                if k == kind and now > deadline:
                    n += 1
        return n

    async def depth_pending(self, kind: JobKind) -> int:
        return self._pending[kind].qsize()

    async def depth_processing(self, kind: JobKind) -> int:
        async with self._lock:
            return sum(1 for k, _, _ in self._leased.values() if k == kind)

    def memory_dlq_snapshot(self, kind: JobKind) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for raw in self._dlq.get(kind, []):
            try:
                out.append(json.loads(raw))
            except Exception:
                out.append({"parse_error": True, "raw": raw[:500]})
        return out

    async def list_dlq(self, kind: JobKind, *, limit: int = 50) -> list[dict[str, Any]]:
        n = max(0, min(int(limit), 500))
        return self.memory_dlq_snapshot(kind)[:n]

    async def replay_dlq_index(self, kind: JobKind, *, index: int) -> bool:
        async with self._lock:
            rows = self._dlq.get(kind, [])
            if index < 0 or index >= len(rows):
                return False
            raw = rows.pop(index)
        try:
            rec = json.loads(raw)
            orig = str(rec.get("original") or "")
            if not orig:
                return False
            env = JobEnvelope.from_json(orig)
            await self.enqueue(env)
            return True
        except Exception as exc:
            logger.warning("reliable_transport.memory_replay_failed kind=%s error=%s", kind.value, repr(exc))
            return False

    async def aclose(self) -> None:
        return None


class RedisReliableTransport:
    def __init__(self, redis_client: Any, *, prefix: str, settings: Any | None = None) -> None:
        self._r = redis_client
        self._prefix = prefix.rstrip(":")
        self._settings = settings

    def _pending(self, kind: JobKind) -> str:
        return f"{self._prefix}:jobq:{kind.value}"

    def _processing(self, kind: JobKind) -> str:
        return f"{self._prefix}:jobq:{kind.value}:processing"

    def _inflight(self, delivery_id: str) -> str:
        return f"{self._prefix}:inflight:{delivery_id}"

    def _dlq(self, kind: JobKind) -> str:
        return f"{self._prefix}:jobq:{kind.value}:dlq"

    async def _redis_call(self, op_name: str, factory: Any) -> Any:
        from utils.redis_resilience import redis_call_with_retry

        return await redis_call_with_retry(factory, self._settings, op_name)

    async def enqueue(self, job: JobEnvelope) -> None:
        j2, _ = _ensure_delivery_id(job)

        async def op() -> None:
            await self._r.lpush(self._pending(job.kind), j2.to_json())

        await self._redis_call("enqueue", op)

    async def lease_dequeue(
        self,
        kind: JobKind,
        *,
        shutdown: asyncio.Event,
        visibility_sec: int,
        poll_timeout_sec: float = 1.0,
    ) -> tuple[str, JobEnvelope] | None:
        from utils.redis_resilience import monotonic_backoff_sleep_sec, redis_transient_error

        t = max(1, int(min(30, round(poll_timeout_sec))) or 1)
        pending, processing = self._pending(kind), self._processing(kind)
        fail_streak = 0
        while not shutdown.is_set():
            try:

                async def br() -> Any:
                    return await self._r.brpoplpush(pending, processing, timeout=t)

                raw = await self._redis_call("brpoplpush", br)
            except Exception as exc:
                fail_streak += 1
                if not redis_transient_error(exc):
                    logger.warning(
                        "reliable_transport.brpoplpush_failed kind=%s error=%s",
                        kind.value,
                        repr(exc),
                    )
                else:
                    logger.warning(
                        "reliable_transport.brpoplpush_degraded kind=%s fail_streak=%s error=%s",
                        kind.value,
                        fail_streak,
                        repr(exc),
                    )
                if shutdown.is_set():
                    return None
                await asyncio.sleep(monotonic_backoff_sleep_sec(min(fail_streak - 1, 12), self._settings))
                continue
            fail_streak = 0
            if raw is None:
                await asyncio.sleep(0)
                continue
            try:
                env = JobEnvelope.from_json(raw)
            except Exception as exc:
                logger.exception("reliable_transport.bad_envelope kind=%s error=%s", kind.value, exc)

                async def lrem_bad() -> None:
                    await self._r.lrem(processing, 1, raw)

                try:
                    await self._redis_call("lrem_bad_envelope", lrem_bad)
                except Exception as exc2:
                    logger.warning("reliable_transport.lrem_bad_envelope_failed error=%s", repr(exc2))
                continue
            j2, did = _ensure_delivery_id(env)
            raw_final = j2.to_json()
            if raw_final != raw:

                async def fix() -> None:
                    await self._r.lrem(processing, 1, raw)
                    await self._r.lpush(processing, raw_final)

                try:
                    await self._redis_call("processing_normalize", fix)
                except Exception as exc2:
                    logger.warning("reliable_transport.processing_normalize_failed error=%s", repr(exc2))
                raw = raw_final
            vis = max(5, int(visibility_sec))
            try:

                async def sx() -> None:
                    await self._r.setex(self._inflight(did), vis, "1")

                await self._redis_call("inflight_setex", sx)
            except Exception as exc:
                logger.warning("reliable_transport.setex_failed delivery_id=%s error=%s", did, repr(exc))
            return raw, JobEnvelope.from_json(raw)
        return None

    async def ack(self, kind: JobKind, raw_exact: str, *, delivery_id: str) -> None:
        processing = self._processing(kind)

        async def op() -> None:
            await self._r.lrem(processing, 1, raw_exact)

        try:
            await self._redis_call("ack_lrem", op)
        finally:

            async def d() -> None:
                await self._r.delete(self._inflight(delivery_id))

            try:
                await self._redis_call("ack_del_inflight", d)
            except Exception:
                pass

    async def nack_requeue(self, kind: JobKind, raw_exact: str, *, delivery_id: str) -> None:
        processing, pending = self._processing(kind), self._pending(kind)

        async def op() -> None:
            await self._r.lrem(processing, 1, raw_exact)
            await self._r.lpush(pending, raw_exact)

        try:
            await self._redis_call("nack_requeue", op)
        finally:

            async def d() -> None:
                await self._r.delete(self._inflight(delivery_id))

            try:
                await self._redis_call("nack_requeue_del_inflight", d)
            except Exception:
                pass

    async def nack_dlq(
        self,
        kind: JobKind,
        raw_exact: str,
        *,
        delivery_id: str,
        reason: str,
        dlq_meta: dict[str, Any] | None = None,
    ) -> None:
        processing = self._processing(kind)
        record = build_dlq_record(
            kind=kind.value,
            delivery_id=delivery_id,
            reason=reason,
            original=raw_exact,
            dlq_meta=dlq_meta,
        )
        payload = json.dumps(record, default=str)

        async def op() -> None:
            await self._r.lrem(processing, 1, raw_exact)
            await self._r.lpush(self._dlq(kind), payload)

        try:
            await self._redis_call("nack_dlq", op)
        finally:

            async def d() -> None:
                await self._r.delete(self._inflight(delivery_id))

            try:
                await self._redis_call("nack_dlq_del_inflight", d)
            except Exception:
                pass
        logger.warning(
            "job.dlq kind=%s delivery_id=%s reason=%s",
            kind.value,
            delivery_id,
            reason[:200],
            extra={"dlq_terminal": (dlq_meta or {}).get("terminal"), "failure_class": (dlq_meta or {}).get("failure_class")},
        )

    async def recover_stale(self, kind: JobKind, *, visibility_sec: int) -> int:
        _ = visibility_sec  # protocol parity; Redis uses inflight TTL
        processing, pending = self._processing(kind), self._pending(kind)

        async def lr() -> list[str]:
            out = await self._r.lrange(processing, 0, -1)
            return list(out or [])

        items = await self._redis_call("recover_lrange", lr)
        moved = 0
        for raw in items or []:
            try:
                env = JobEnvelope.from_json(raw)
                did = str(env.payload.get("delivery_id") or "")
                if not did:
                    continue

                async def ex() -> int:
                    return int(await self._r.exists(self._inflight(did)) or 0)

                exists = await self._redis_call("recover_exists", ex)
                if not exists:

                    async def mv() -> None:
                        pipe = self._r.pipeline(transaction=True)
                        pipe.lrem(processing, 1, raw)
                        pipe.lpush(pending, raw)
                        await pipe.execute()

                    await self._redis_call("recover_move", mv)
                    moved += 1
            except Exception as exc:
                logger.warning("reliable_transport.recover_item_failed kind=%s error=%s", kind.value, repr(exc))
        return moved

    async def count_recoverable_stale(self, kind: JobKind, *, visibility_sec: int) -> int:
        _ = visibility_sec
        processing = self._processing(kind)

        async def lr() -> list[str]:
            out = await self._r.lrange(processing, 0, -1)
            return list(out or [])

        items = await self._redis_call("count_recover_lrange", lr)
        n = 0
        for raw in items or []:
            try:
                env = JobEnvelope.from_json(raw)
                did = str(env.payload.get("delivery_id") or "")
                if not did:
                    continue

                async def ex() -> int:
                    return int(await self._r.exists(self._inflight(did)) or 0)

                exists = await self._redis_call("count_recover_exists", ex)
                if not exists:
                    n += 1
            except Exception:
                continue
        return n

    async def depth_pending(self, kind: JobKind) -> int:

        async def op() -> int:
            return int(await self._r.llen(self._pending(kind)) or 0)

        return int(await self._redis_call("depth_pending", op))

    async def depth_processing(self, kind: JobKind) -> int:

        async def op() -> int:
            return int(await self._r.llen(self._processing(kind)) or 0)

        return int(await self._redis_call("depth_processing", op))

    async def list_dlq(self, kind: JobKind, *, limit: int = 50) -> list[dict[str, Any]]:
        n = max(0, min(int(limit), 500))

        async def op() -> list[str]:
            if n <= 0:
                return []
            return list(await self._r.lrange(self._dlq(kind), 0, n - 1) or [])

        raw_rows = await self._redis_call("list_dlq", op)
        out: list[dict[str, Any]] = []
        for r in raw_rows:
            try:
                out.append(json.loads(r))
            except Exception:
                out.append({"parse_error": True, "raw": str(r)[:500]})
        return out

    async def replay_dlq_index(self, kind: JobKind, *, index: int) -> bool:
        if index < 0:
            return False

        async def one() -> str | None:
            rows = await self._r.lrange(self._dlq(kind), index, index)
            return str(rows[0]) if rows else None

        raw = await self._redis_call("replay_dlq_peek", one)
        if not raw:
            return False
        try:
            rec = json.loads(raw)
            orig = str(rec.get("original") or "")
            if not orig:
                return False
            env = JobEnvelope.from_json(orig)
        except Exception as exc:
            logger.warning("reliable_transport.replay_parse_failed kind=%s error=%s", kind.value, repr(exc))
            return False

        async def lrem() -> int:
            return int(await self._r.lrem(self._dlq(kind), 1, raw) or 0)

        removed = await self._redis_call("replay_dlq_lrem", lrem)
        if removed < 1:
            return False
        await self.enqueue(env)
        return True

    async def aclose(self) -> None:
        return None


_transport: ReliableJobTransport | None = None


def reset_reliable_transport_for_tests() -> None:
    global _transport
    _transport = None


def get_reliable_transport() -> ReliableJobTransport:
    if _transport is None:
        raise RuntimeError("Reliable transport not initialized; call init_reliable_transport first")
    return _transport


async def init_reliable_transport(settings: Any) -> None:
    global _transport
    if _transport is not None:
        return
    from utils.redis_client import get_redis

    r = await get_redis()
    prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom")
    if r is not None and bool(getattr(settings, "redis_enabled", False)):
        _transport = RedisReliableTransport(r, prefix=prefix, settings=settings)
        logger.info("reliable_transport.initialized mode=redis")
    else:
        _transport = InMemoryReliableTransport()
        logger.info("reliable_transport.initialized mode=memory")


async def close_reliable_transport() -> None:
    global _transport
    if _transport is None:
        return
    try:
        await _transport.aclose()
    finally:
        _transport = None
        logger.info("reliable_transport.closed")
