"""Worker heartbeat keys in Redis (optional)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


async def write_worker_heartbeat(settings: Any, role: str) -> None:
    """SET key with TTL; no-op without Redis."""
    from utils.redis_client import get_redis

    r = await get_redis()
    if r is None:
        return
    prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom").rstrip(":")
    ttl = int(getattr(settings, "worker_heartbeat_ttl_sec", 90) or 90)
    key = f"{prefix}:worker:hb:{role}"
    try:
        await r.set(key, str(int(time.time())), ex=max(15, ttl))
    except Exception as exc:
        logger.warning("worker.heartbeat_write_failed role=%s error=%s", role, repr(exc))


async def read_worker_heartbeat_age_sec(settings: Any, role: str) -> float | None:
    """Seconds since epoch value in key, or None if missing / no Redis."""
    from utils.redis_client import get_redis

    r = await get_redis()
    if r is None:
        return None
    prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom").rstrip(":")
    key = f"{prefix}:worker:hb:{role}"
    try:
        raw = await r.get(key)
        if raw is None:
            return None
        ts = float(raw)
        return max(0.0, time.time() - ts)
    except Exception:
        return None


async def write_worker_runtime_detail(settings: Any, role: str, detail: dict[str, Any]) -> None:
    """Optional JSON snapshot for observability (Redis)."""
    import json

    from utils.redis_client import get_redis

    r = await get_redis()
    if r is None:
        return
    prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom").rstrip(":")
    iid = str(getattr(settings, "worker_instance_id", "default"))[:120]
    ttl = int(getattr(settings, "worker_heartbeat_ttl_sec", 90) or 90)
    key = f"{prefix}:worker:runtime:{role}:{iid}"
    try:
        await r.setex(key, max(15, ttl), json.dumps(detail, default=str))
    except Exception as exc:
        logger.warning("worker.runtime_detail_write_failed role=%s error=%s", role, repr(exc))


async def gather_worker_runtime_snapshot(settings: Any, role: str) -> dict[str, Any]:
    """Queue lag + heartbeat + last written runtime detail + in-process counters."""
    import json

    from worker.job_queue import JobKind

    from workers import state as worker_state

    out: dict[str, Any] = {
        "role": role,
        "ts": time.time(),
        "heartbeat_age_sec": await read_worker_heartbeat_age_sec(settings, role),
        "counters": worker_state.runtime_counters_snapshot(),
    }
    try:
        kind = JobKind(role)
        try:
            from worker.reliable_transport import get_reliable_transport

            t = get_reliable_transport()
            out["queues"] = {
                "pending": await t.depth_pending(kind),
                "processing": await t.depth_processing(kind),
            }
        except RuntimeError:
            out["queues"] = {"mode": "transport_uninitialized"}
    except Exception as exc:
        out["queues"] = {"error": repr(exc)}

    try:
        from utils.redis_client import get_redis

        r = await get_redis()
        if r is not None:
            prefix = str(getattr(settings, "job_queue_prefix", "newsroom") or "newsroom").rstrip(":")
            iid = str(getattr(settings, "worker_instance_id", "default"))[:120]
            raw = await r.get(f"{prefix}:worker:runtime:{role}:{iid}")
            if raw:
                out["last_runtime_detail"] = json.loads(raw)
    except Exception as exc:
        out["last_runtime_detail_error"] = repr(exc)
    return out

