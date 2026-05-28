"""Pipeline tick persistence and stuck-tick detection."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any

from db.reliability_repository import (
    complete_pipeline_tick,
    insert_pipeline_tick_start,
    latest_pipeline_tick,
)
from ops.operator_notifications import enqueue_operator_notification
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _stuck_threshold_sec() -> float:
    raw = os.getenv("PIPELINE_TICK_STUCK_SEC", "1200").strip()
    try:
        return max(120.0, min(float(raw), 86400.0))
    except ValueError:
        return 1200.0


def _long_running_warn_sec() -> float:
    raw = os.getenv("PIPELINE_TICK_LONG_WARN_SEC", "600").strip()
    try:
        return max(60.0, min(float(raw), 7200.0))
    except ValueError:
        return 600.0


def node_name() -> str:
    return (os.getenv("RUNTIME_OWNER_ID") or socket.gethostname())[:128]


async def begin_persisted_tick(*, tick_id: str, correlation_id: str) -> None:
    try:
        from app.observability.execution_graph_trace import record_tick_begin

        record_tick_begin(tick_id)
    except Exception:
        pass
    try:
        await insert_pipeline_tick_start(
            tick_id=tick_id,
            node_name=node_name(),
            correlation_id=correlation_id,
        )
    except Exception as exc:
        log_event(logger, "pipeline_tick.persist_start_failed", tick_id=tick_id, error=repr(exc)[:200])


async def finish_persisted_tick(
    tick_id: str,
    *,
    drafts_created: int,
    posts_collected: int,
    failures: int,
    status: str,
    detail: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    try:
        await complete_pipeline_tick(
            tick_id,
            drafts_created=drafts_created,
            posts_collected=posts_collected,
            failures=failures,
            status=status,
            detail=detail,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        log_event(logger, "pipeline_tick.persist_finish_failed", tick_id=tick_id, error=repr(exc)[:200])


async def check_stuck_pipeline_ticks(settings: Any) -> dict[str, Any]:
    """Finalize stale running ticks with committed_reject (heartbeat)."""
    from app.reliability.stale_tick_recovery import reconcile_stale_pipeline_ticks

    recovery = await reconcile_stale_pipeline_ticks(settings, source="watchdog")
    marked: list[str] = list(recovery.get("finalized") or [])
    for tid in marked:
        log_event(logger, "pipeline_tick.stale", tick_id=tid, recovery="committed_reject")
    latest = await latest_pipeline_tick()
    long_warn = False
    if latest and latest.status == "running" and latest.started_at:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        age = (now - latest.started_at).total_seconds()
        if age > _long_running_warn_sec():
            long_warn = True
            enqueue_operator_notification(
                settings.runtime_state_dir,
                kind="pipeline_long_running",
                severity="warn",
                message=f"Pipeline tick running {int(age)}s (tick_id={latest.tick_id})",
                fields={"tick_id": latest.tick_id, "age_sec": int(age)},
            )
    return {"stale_marked": marked, "long_running_warn": long_warn}


def last_tick_summary() -> dict[str, Any]:
    """Sync helper for ops panel (reads via asyncio in caller)."""
    return {"note": "use async latest_pipeline_tick via operator_summary"}
