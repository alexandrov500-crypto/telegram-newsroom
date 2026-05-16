"""Queue depth / lag / inflight age samples (best-effort; Redis-aware)."""

from __future__ import annotations

import time
from typing import Any

from worker.job_queue import JobEnvelope, JobKind
from worker.reliable_transport import RedisReliableTransport, ReliableJobTransport


async def collect_queue_pressure(
    transport: ReliableJobTransport,
    kind: JobKind,
    settings: Any,
) -> dict[str, Any]:
    pending = int(await transport.depth_pending(kind))
    processing = int(await transport.depth_processing(kind))
    out: dict[str, Any] = {
        "job_kind": kind.value,
        "pending_depth": pending,
        "processing_depth": processing,
        "oldest_pending_age_sec": None,
        "sample_inflight_age_sec": None,
        "inflight_sample_count": 0,
        "recoverable_processing_estimate": None,
        "redis_transport_metrics": {},
    }
    try:
        from utils.redis_transport_metrics import snapshot as rtm_snap

        out["redis_transport_metrics"] = rtm_snap()
    except Exception:
        pass

    vis = max(5, int(getattr(settings, "worker_visibility_sec", 120)))
    if hasattr(transport, "count_recoverable_stale"):
        try:
            out["recoverable_processing_estimate"] = int(
                await transport.count_recoverable_stale(kind, visibility_sec=vis),
            )
        except Exception:
            pass
    if not isinstance(transport, RedisReliableTransport):
        return out

    r = transport._r
    pk = transport._pending(kind)
    proc_k = transport._processing(kind)

    async def lindex_tail() -> str | None:
        raw = await r.lindex(pk, -1)
        return str(raw) if raw else None

    try:
        raw_tail = await transport._redis_call("diag_lindex_pending", lindex_tail)
        if raw_tail:
            env = JobEnvelope.from_json(raw_tail)
            ts = float(env.payload.get("_enqueue_wall_ts") or 0)
            if ts > 0:
                out["oldest_pending_age_sec"] = round(max(0.0, time.time() - ts), 3)
    except Exception:
        pass

    ages: list[float] = []

    async def sample_proc() -> list[str]:
        return list(await r.lrange(proc_k, 0, 4) or [])

    try:
        samples = await transport._redis_call("diag_lrange_processing", sample_proc)
        for raw in samples or []:
            try:
                env = JobEnvelope.from_json(raw)
                did = str(env.payload.get("delivery_id") or "")
                if not did:
                    continue
                inflight_key = transport._inflight(did)

                async def ttl_op() -> int:
                    return int(await r.ttl(inflight_key))

                ttl = await transport._redis_call("diag_inflight_ttl", ttl_op)
                if ttl > 0:
                    ages.append(float(vis - ttl))
            except Exception:
                continue
        if ages:
            out["sample_inflight_age_sec"] = round(sum(ages) / len(ages), 3)
            out["inflight_sample_count"] = len(ages)
    except Exception:
        pass

    return out


def queue_saturation_warnings(settings: Any, pressure: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured warning dicts (caller should log_event)."""
    warns: list[dict[str, Any]] = []
    p = int(pressure.get("pending_depth") or 0)
    pr = int(pressure.get("processing_depth") or 0)
    lim_p = int(getattr(settings, "runtime_queue_pending_warn", 500))
    lim_pr = int(getattr(settings, "runtime_queue_processing_warn", 50))
    if p >= lim_p:
        warns.append(
            {
                "code": "queue_pending_high",
                "pending_depth": p,
                "threshold": lim_p,
            }
        )
    if pr >= lim_pr:
        warns.append(
            {
                "code": "queue_processing_high",
                "processing_depth": pr,
                "threshold": lim_pr,
            }
        )
    lag = pressure.get("oldest_pending_age_sec")
    lag_lim = float(getattr(settings, "runtime_queue_lag_warn_sec", 600))
    if lag is not None and float(lag) >= lag_lim:
        warns.append(
            {
                "code": "queue_lag_high",
                "oldest_pending_age_sec": float(lag),
                "threshold_sec": lag_lim,
            }
        )
    growth = int(getattr(settings, "runtime_queue_growth_warn_depth", 2000))
    if p >= growth:
        warns.append(
            {
                "code": "queue_growth_alert",
                "pending_depth": p,
                "threshold": growth,
            }
        )
    return warns


def queue_drift_warnings(settings: Any, pressure: dict[str, Any]) -> list[dict[str, Any]]:
    """Heuristic consistency warnings (best-effort; no automatic repair)."""
    warns: list[dict[str, Any]] = []
    p = int(pressure.get("pending_depth") or 0)
    est = pressure.get("recoverable_processing_estimate")
    if est is not None and int(est) > 0:
        warns.append(
            {
                "code": "inflight_orphans_estimated",
                "recoverable_processing_estimate": int(est),
            }
        )
    if p >= 50 and pressure.get("oldest_pending_age_sec") is None:
        warns.append(
            {
                "code": "queue_timestamp_unavailable",
                "pending_depth": p,
                "hint": "tail pending jobs missing _enqueue_wall_ts; lag metrics degraded",
            }
        )
    return warns
