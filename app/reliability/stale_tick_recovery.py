"""Finalize orphaned pipeline_ticks rows (running past TTL) with deterministic terminal state."""

from __future__ import annotations

import logging
import os
from typing import Any

from db.reliability_repository import finalize_stale_pipeline_ticks
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def max_tick_runtime_sec() -> float:
    raw = os.getenv("MAX_TICK_RUNTIME_SEC", "").strip()
    if raw:
        try:
            return max(120.0, min(float(raw), 86400.0))
        except ValueError:
            pass
    raw2 = os.getenv("PIPELINE_TICK_STUCK_SEC", "1200").strip()
    try:
        return max(120.0, min(float(raw2), 86400.0))
    except ValueError:
        return 1200.0


async def reconcile_stale_pipeline_ticks(
    settings: Any,
    *,
    source: str = "watchdog",
    older_than_sec: float | None = None,
) -> dict[str, Any]:
    """
    Detect running ticks older than threshold and finalize as committed_reject.

    Idempotent: only updates rows still in status=running.
    """
    threshold = max_tick_runtime_sec() if older_than_sec is None else max(30.0, min(older_than_sec, 86400.0))
    stuck = await finalize_stale_pipeline_ticks(
        older_than_sec=threshold,
        terminal_reason="stale_tick_timeout",
    )
    finalized: list[str] = []
    for row in stuck:
        tid = str(row.get("tick_id") or "")
        age = row.get("age_sec")
        log_event(
            logger,
            "pipeline.stale_tick_detected",
            tick_id=tid,
            age_sec=age,
            threshold_sec=threshold,
            source=source,
        )
        log_event(
            logger,
            "pipeline.stale_tick_finalized",
            tick_id=tid,
            status="reject",
            terminal_state="committed_reject",
            terminal_reason="stale_tick_timeout",
            source=source,
        )
        finalized.append(tid)

    if finalized:
        try:
            from ops.operator_notifications import enqueue_operator_notification

            enqueue_operator_notification(
                settings.runtime_state_dir,
                kind="pipeline_stale_ticks_finalized",
                severity="warn",
                message=f"Finalized {len(finalized)} stale pipeline tick(s)",
                fields={"tick_ids": finalized[:8], "count": len(finalized)},
            )
        except Exception:
            pass

    return {
        "threshold_sec": threshold,
        "finalized": finalized,
        "count": len(finalized),
        "source": source,
    }
