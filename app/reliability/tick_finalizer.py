"""Single terminal-state finalization per pipeline tick."""

from __future__ import annotations

import logging
from typing import Any

from scheduler.runtime_context import PipelineContext
from app.reliability.terminal_state_resolver import TERMINAL_STATES
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _enforce_backlog_tick_accountability(ctx: PipelineContext, resolution: object) -> None:
    from app.recovery.pipeline_context_builder import build_pipeline_decision_context
    from app.reliability.terminal_state_resolver import TerminalStateResolution
    from app.state.pipeline_decision_engine import (
        apply_pipeline_decision,
        log_pipeline_decision_trace,
        make_pipeline_decision,
    )

    pctx = build_pipeline_decision_context()
    res = resolution if isinstance(resolution, TerminalStateResolution) else resolution
    if res.terminal_state == "committed_draft":
        pd = ctx.pipeline_decision or make_pipeline_decision(pctx)
        log_pipeline_decision_trace(
            pctx,
            pd,
            source="tick_accountability",
            final_action=f"draft_created:{ctx.tick_draft_id}",
        )
        return
    if res.terminal_state == "committed_reject":
        log_event(
            logger,
            "pipeline.backlog_explicit_reject",
            raw_unprocessed=pctx.raw_unprocessed,
            reason=res.reason,
            terminal_state=res.terminal_state,
            publish_outcome=ctx.tick_publish_outcome,
        )
        pd = ctx.pipeline_decision or apply_pipeline_decision(ctx, source="tick_accountability_reject")
        log_pipeline_decision_trace(
            pctx,
            pd,
            source="tick_accountability",
            final_action=f"rejected:{res.reason[:120]}",
        )


async def finalize_pipeline_tick(ctx: PipelineContext, settings: Any) -> None:
    """One resolver + one persist finish — terminal state ∈ {draft, reject, idle}."""
    from app.observability.execution_graph_trace import (
        complete_execution_graph_trace,
        record_finalize_begin,
    )

    record_finalize_begin()
    from app.recovery.pipeline_context_builder import build_pipeline_decision_context
    from app.reliability.pipeline_ticks import finish_persisted_tick
    from app.reliability.terminal_state_resolver import resolve_terminal_state
    from utils.operational_context import current_tick_id

    pctx = build_pipeline_decision_context()
    terminal = resolve_terminal_state(ctx, raw_unprocessed=pctx.raw_unprocessed)
    assert terminal.terminal_state in TERMINAL_STATES

    log_event(
        logger,
        "pipeline.terminal_state",
        terminal_state=terminal.terminal_state,
        tick_status=terminal.tick_status,
        reason=terminal.reason[:240],
        draft_id=ctx.tick_draft_id,
    )
    _enforce_backlog_tick_accountability(ctx, terminal)

    tid = current_tick_id() or "unknown"
    graph_meta = complete_execution_graph_trace(
        terminal_state=terminal.terminal_state,
        tick_id=tid,
        runtime_dir=settings.runtime_state_dir,
    )

    detail = terminal.to_detail(ctx)
    detail["execution_graph"] = graph_meta

    tick_status = terminal.tick_status if terminal.tick_status in ("ok", "reject") else (
        "reject" if terminal.terminal_state == "committed_reject" else "ok"
    )
    if graph_meta.get("corrupted"):
        tick_status = "reject"
        detail["terminal_state"] = "committed_reject"
        detail["terminal_reason"] = (
            "execution_graph_corrupted:"
            + ",".join((graph_meta.get("anomaly_critical") or [])[:3])
        )[:240]
        detail["execution_graph_corrupted"] = True
        ctx.tick_summarize_idle_reason = detail["terminal_reason"]
        log_event(
            logger,
            "execution_graph.tick_marked_corrupted",
            tick_id=tid,
            critical=graph_meta.get("anomaly_critical"),
        )

    await finish_persisted_tick(
        tid,
        drafts_created=0 if graph_meta.get("corrupted") else terminal.drafts_created,
        posts_collected=int(ctx.tick_collect_rows or 0),
        failures=max(int(getattr(ctx, "tick_failures", 0) or 0), 1 if graph_meta.get("corrupted") else 0),
        status=tick_status,
        detail=detail,
    )
    try:
        from app.observability.runtime_health import record_tick_duration

        wall = float(getattr(ctx, "last_scheduler_wall_sec", 0) or 0)
        if wall > 0:
            record_tick_duration(wall)
        db_sec = float((ctx.tick_timings or {}).get("db_fetch_unprocessed_sec") or 0)
        if db_sec > 0:
            from app.observability.runtime_health import record_db_latency_ms

            record_db_latency_ms(db_sec * 1000.0)
    except Exception:
        pass
