"""Merge runtime + editorial + warnings for HTTP / CLI / exports."""

from __future__ import annotations

import time
from typing import Any

from app.config import Settings

from dashboard.editorial_dashboard import build_editorial_dashboard
from dashboard.models import OperationalDashboardBundle
from dashboard.runtime_dashboard import build_runtime_dashboard
from dashboard.timeline import load_timeline_tail
from observability.runtime_warnings import collect_runtime_warnings
from utils.editorial_analytics import export_editorial_analytics


async def build_operational_dashboard_bundle(
    settings: Settings,
    *,
    include_openai: bool = False,
) -> OperationalDashboardBundle:
    runtime = await build_runtime_dashboard(settings, include_openai=include_openai)
    editorial = build_editorial_dashboard(settings)
    warns = collect_runtime_warnings(settings, runtime_health=runtime.get("health"), metrics_export=runtime.get("metrics_export"))
    tail = load_timeline_tail(settings.runtime_state_dir, limit=40)
    ctr = dict((runtime.get("metrics_export") or {}).get("counters") or {})
    ed_op = export_editorial_analytics(ctr)
    return OperationalDashboardBundle(
        generated_at_unix=time.time(),
        runtime=runtime,
        editorial=editorial,
        warnings=warns,
        timeline_tail=tail,
        editorial_operational=ed_op,
    )
