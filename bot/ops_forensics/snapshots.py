from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def capture_runtime_snapshot() -> dict[str, Any]:
    """Collect point-in-time runtime state for drift and incident analysis."""
    now = datetime.now(timezone.utc).isoformat()
    snap: dict[str, Any] = {"timestamp": now}

    try:
        from bot.runtime.instance import get_runtime_identity

        ident = get_runtime_identity()
        if ident is not None:
            snap["runtime_instance_id"] = ident.runtime_instance_id
            snap["runtime_profile"] = ident.runtime_profile
            snap["pid"] = ident.pid
    except Exception:
        pass

    try:
        from bot.runtime.profile import get_runtime_capabilities

        snap["runtime_profile"] = snap.get("runtime_profile") or get_runtime_capabilities().profile.value
    except Exception:
        pass

    try:
        from bot.observability.loop_diagnostics import snapshot as loop_diag
        from bot.observability.loop_health import snapshot as loop_health

        snap["loop_diagnostics"] = loop_diag()
        snap["loop_health"] = loop_health()
    except Exception:
        pass

    try:
        from bot.observability.loop_registry import get_loop_registry

        reg = get_loop_registry()
        snap["loops"] = reg.runtime_loops_view()
        snap["stalled"] = reg.watchdog_stalled_names()
    except Exception:
        pass

    snap["queue_backlog"] = None

    try:
        from bot.live_ops.context_holder import get_controlled_live

        cl = get_controlled_live()
        if cl is not None:
            snap["channel_state"] = cl.repository.get_state()
            snap["channel_health"] = cl.feedback.scores()
    except Exception:
        pass

    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if rss > 10_000_000:
            snap["memory_mb"] = round(rss / (1024 * 1024), 2)
        else:
            snap["memory_mb"] = round(rss / 1024, 2)
    except Exception:
        snap["memory_mb"] = None

    snap["recovery_attempt_count"] = (snap.get("loop_health") or {}).get("recovery_attempt_count")
    return snap


async def runtime_snapshot_loop(*, interval_sec: int | None = None) -> None:
    import asyncio

    from bot.ops_forensics.repository import ForensicsRepository

    interval = interval_sec or int(os.getenv("RUNTIME_SNAPSHOT_INTERVAL_SEC", "300"))
    repo = ForensicsRepository()
    logger.info("event=runtime_snapshot_loop_started interval_sec=%s", interval)
    while True:
        try:
            snap = capture_runtime_snapshot()
            repo.save_runtime_snapshot(snap)
        except Exception:
            logger.exception("event=runtime_snapshot_failed")
        await asyncio.sleep(interval)
