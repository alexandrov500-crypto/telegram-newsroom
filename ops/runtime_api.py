"""Read-only JSON handlers for GET /runtime/* operational endpoints."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.build_provenance import load_build_provenance
from app.dependency_state import get_dependency_state
from app.openai_circuit import get_openai_circuit
from app.runtime_activity import activity_snapshot
from app.runtime_lifecycle import runtime_id, uptime_sec
from app.runtime_metrics import export_merged_metrics
from ops.runtime_timeline import timeline_snapshot, watchdog_alerts_total


def _json_response(obj: Any) -> tuple[int, str, bytes]:
    return 200, "application/json", json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


async def runtime_status_payload() -> dict[str, Any]:
    prov = load_build_provenance()
    deps = get_dependency_state()
    return {
        "service": "newsroom",
        "runtime_id": runtime_id(),
        "uptime_sec": round(uptime_sec(), 2),
        "git_sha": prov.git_sha,
        "build_version": prov.build_version,
        "build_branch": prov.build_branch,
        "aggregate_status": deps.aggregate_status().value,
        "startup_complete": deps.startup_complete,
        "ai_pipeline_enabled": deps.ai_pipeline_enabled,
        "collector_enabled": deps.collector_enabled,
        "polling_active": deps.polling_active,
        "activity": activity_snapshot(),
    }


async def runtime_watchdog_payload() -> dict[str, Any]:
    from app.runtime_activity import (
        exception_count_in_window,
        seconds_since_collect,
        seconds_since_scheduler_tick,
    )

    return {
        "alerts_total": watchdog_alerts_total(),
        "exception_burst_count": exception_count_in_window(300.0),
        "seconds_since_scheduler_tick": seconds_since_scheduler_tick(),
        "seconds_since_collect": seconds_since_collect(),
    }


async def runtime_queues_payload(settings: Any) -> dict[str, Any]:
    from utils.metrics import export_snapshot
    from worker.job_queue import JobKind, get_job_queue

    snap = export_snapshot()
    depths: dict[str, int] = {}
    try:
        q = get_job_queue()
        for k in JobKind:
            depths[k.value] = int(await q.depth(k))
    except Exception as exc:
        depths["error"] = repr(exc)[:200]
    return {
        "queue_depth_total": int((snap.get("gauges") or {}).get("queue_depth", 0)),
        "depth_by_kind": depths,
        "overflow_total": int((snap.get("counters") or {}).get("queue_overflow_total", 0)),
        "max_size": int(getattr(settings, "job_queue_max_size", 500)),
    }


def runtime_circuit_payload() -> dict[str, Any]:
    return {"circuit": get_openai_circuit().snapshot(), "metrics": {
        k: (export_merged_metrics().get("counters") or {}).get(k, 0)
        for k in ("openai_failures_total", "openai_recovery_attempts_total")
    }, "gauges": {
        k: (export_merged_metrics().get("gauges") or {}).get(k, 0)
        for k in ("openai_circuit_open",)
    }}


def runtime_timeline_payload(*, limit: int = 100) -> dict[str, Any]:
    return {
        "count": len(timeline_snapshot(limit=limit)),
        "entries": timeline_snapshot(limit=limit),
    }


def list_recent_incidents(settings: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    d = Path(str(getattr(settings, "runtime_state_dir", "var/runtime"))) / "incidents"
    if not d.is_dir():
        return []
    files = sorted(d.glob("incident_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for p in files[:limit]:
        st = p.stat()
        out.append({
            "name": p.name,
            "path": str(p),
            "size_bytes": st.st_size,
            "mtime_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        })
    return out


async def dispatch_runtime_http(
    settings: Any,
    path_only: str,
) -> tuple[int, str, bytes] | None:
    p = path_only.rstrip("/")
    if p == "/runtime/status":
        return _json_response(await runtime_status_payload())
    if p == "/runtime/watchdog":
        return _json_response(await runtime_watchdog_payload())
    if p == "/runtime/queues":
        return _json_response(await runtime_queues_payload(settings))
    if p == "/runtime/circuit":
        return _json_response(runtime_circuit_payload())
    if p == "/runtime/timeline":
        return _json_response(runtime_timeline_payload())
    if p == "/runtime/incidents":
        return _json_response({"bundles": list_recent_incidents(settings)})
    from ops.editorial_runtime_api import dispatch_editorial_runtime_http

    ed = await dispatch_editorial_runtime_http(settings, path_only)
    if ed is not None:
        return ed
    return None
