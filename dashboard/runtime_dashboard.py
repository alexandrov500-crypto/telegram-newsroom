"""Read-only runtime slice for dashboards (workers, queues, metrics tail)."""

from __future__ import annotations

import time
from typing import Any

from app.config import Settings


async def build_runtime_dashboard(settings: Settings, *, include_openai: bool = False) -> dict[str, Any]:
    from utils.metrics import export_snapshot
    from utils.runtime_events import get_recent_runtime_events
    from utils.runtime_health import gather_runtime_health

    health = await gather_runtime_health(settings, include_openai=include_openai)
    snap = export_snapshot()
    events = get_recent_runtime_events(64)
    warnish = [e for e in events if any(x in str(e.get("kind") or "") for x in ("fail", "error", "dlq", "retry", "storm"))]
    return {
        "schema_version": 1,
        "ts": time.time(),
        "health": health,
        "metrics_export": snap,
        "recent_runtime_events": events[-24:],
        "recent_warnish_events": warnish[-16:],
    }
