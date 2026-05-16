"""Read-only job queue and publish-lock visibility."""

from __future__ import annotations

import json
import time
from typing import Any

from worker.job_queue import JobKind


async def collect_queue_introspection(settings: Any) -> dict[str, Any]:
    """Inspect queues and locks without dequeue, retry, or mutations."""
    from utils.metrics import export_snapshot
    from utils.reliability_diagnostics import lock_events_snapshot, retry_traces_snapshot
    from utils.redis_client import get_redis

    prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom").rstrip(":")
    redis_enabled = bool(getattr(settings, "redis_enabled", False))
    r = await get_redis()

    per_kind: dict[str, Any] = {}
    for kind in JobKind:
        row: dict[str, Any] = {"kind": kind.value}
        if r is not None and redis_enabled:
            pending_k = f"{prefix}:jobq:{kind.value}"
            proc_k = f"{prefix}:jobq:{kind.value}:processing"
            dlq_k = f"{prefix}:jobq:{kind.value}:dlq"
            try:
                row["pending_count"] = int(await r.llen(pending_k) or 0)
                row["processing_count"] = int(await r.llen(proc_k) or 0)
                row["dlq_count"] = int(await r.llen(dlq_k) or 0)
                oldest = await _oldest_enqueue_age_sec(r, pending_k)
                row["oldest_pending_age_sec"] = oldest
            except Exception as exc:
                row["error"] = repr(exc)
        else:
            row.update(await _memory_queue_stats(kind))
        per_kind[kind.value] = row

    locks = await _publish_lock_scan(r, prefix) if r is not None and redis_enabled else []

    retry_burst = 0
    try:
        from workers import state as worker_state

        diag = await worker_state.collect_runtime_diag(settings)
        retry_burst = int(diag.get("retry_burst_window", 0))
    except Exception:
        pass

    snap = export_snapshot().get("counters") or {}
    return {
        "schema_version": 1,
        "read_only": True,
        "no_redis_mutations": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport_mode": "redis" if r is not None and redis_enabled else "memory",
        "queues": per_kind,
        "publish_locks": locks,
        "retry_amplification": {
            "retry_burst_window": retry_burst,
            "publish_retries_total": int(snap.get("publish_retries", 0)),
            "worker_retry_safe_reorders": int(snap.get("worker_retry_safe_reorders", 0)),
            "retry_traces_sampled": len(retry_traces_snapshot()),
        },
        "lock_events_sampled": len(lock_events_snapshot()),
    }


async def _memory_queue_stats(kind: JobKind) -> dict[str, Any]:
    pending: int | None = None
    try:
        from worker.job_queue import get_job_queue

        pending = await get_job_queue().depth(kind)
    except Exception:
        pending = None
    return {
        "pending_count": pending,
        "processing_count": None,
        "dlq_count": None,
        "note": "memory_mode_or_queue_not_initialized",
    }


async def _oldest_enqueue_age_sec(redis: Any, list_key: str) -> float | None:
    raw = await redis.lindex(list_key, -1)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        inner = payload.get("payload") if isinstance(payload, dict) else {}
        ts = float((inner or {}).get("_enqueue_wall_ts") or 0)
        if ts <= 0:
            return None
        return round(max(0.0, time.time() - ts), 3)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


async def _publish_lock_scan(redis: Any, prefix: str, *, limit: int = 32) -> list[dict[str, Any]]:
    pattern = f"{prefix}:publish_lock:*"
    out: list[dict[str, Any]] = []
    try:
        async for key in redis.scan_iter(match=pattern, count=64):
            k = key.decode() if isinstance(key, bytes) else str(key)
            ttl = await redis.ttl(k)
            draft_part = k.rsplit(":", 1)[-1]
            out.append(
                {
                    "key_suffix": draft_part,
                    "ttl_sec": int(ttl) if ttl is not None else None,
                }
            )
            if len(out) >= limit:
                break
    except Exception:
        return out
    return out
