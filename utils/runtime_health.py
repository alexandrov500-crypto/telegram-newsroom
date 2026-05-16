"""Runtime readiness / health snapshots (DB, Redis, job queues) for CLI, Docker, or HTTP."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text

from app.config import Settings
from utils.database_url import database_backend_label
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def gather_runtime_health(settings: Settings, *, include_openai: bool = False) -> dict[str, Any]:
    """
    Non-fatal checks suitable for readiness probes.
    ``include_openai`` stays False for Docker/db-only probes.
    """
    out: dict[str, Any] = {
        "ok": True,
        "ts": time.time(),
        "database_backend": database_backend_label(settings.database_url),
        "checks": {},
    }

    try:
        from db.session import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        out["checks"]["database"] = {"ok": True}
    except Exception as exc:
        out["ok"] = False
        out["checks"]["database"] = {"ok": False, "error": repr(exc)}

    try:
        from utils.redis_client import get_redis, redis_ping_ok

        r = await get_redis()
        if r is None:
            out["checks"]["redis"] = {
                "ok": True,
                "mode": "disabled" if not settings.redis_enabled else "degraded_connect_failed",
            }
        else:
            ping = await redis_ping_ok()
            ok = ping is True
            out["checks"]["redis"] = {"ok": ok, "mode": "enabled"}
            if not ok:
                out["ok"] = False
    except Exception as exc:
        out["checks"]["redis"] = {"ok": False, "error": repr(exc)}

    try:
        from utils.redis_transport_metrics import snapshot as rtm_snap

        out["checks"]["redis_transport_metrics"] = {"ok": True, **rtm_snap()}
    except Exception as exc:
        out["checks"]["redis_transport_metrics"] = {"ok": False, "error": repr(exc)}

    depths: dict[str, int] = {}
    try:
        from worker.job_queue import JobKind, get_job_queue

        q = get_job_queue()
        for k in JobKind:
            depths[k.value] = await q.depth(k)
        out["checks"]["queues"] = {"ok": True, "depth_by_kind": depths}
    except RuntimeError:
        out["checks"]["queues"] = {"ok": True, "depth_by_kind": {}, "mode": "uninitialized"}
    except Exception as exc:
        out["checks"]["queues"] = {"ok": False, "error": repr(exc)}

    hb: dict[str, Any] = {}
    try:
        from worker import heartbeat

        for role in ("ingest", "ai", "publisher"):
            age = await heartbeat.read_worker_heartbeat_age_sec(settings, role)
            hb[role] = {"age_sec": age}
        out["checks"]["worker_heartbeat"] = {"ok": True, "roles": hb}
    except Exception as exc:
        out["checks"]["worker_heartbeat"] = {"ok": False, "error": repr(exc)}

    try:
        from utils.runtime_reports import build_ai_governance_report

        out["checks"]["ai_governance"] = build_ai_governance_report(settings)
    except Exception as exc:
        out["checks"]["ai_governance"] = {"ok": False, "error": repr(exc)}

    log_event(logger, "runtime_health.snapshot", ok=out["ok"], backend=out["database_backend"])
    return out
