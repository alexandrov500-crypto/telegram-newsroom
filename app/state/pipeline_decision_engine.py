"""
Deterministic pipeline decision engine — sole execution authority.

Boolean flags (ai_pipeline_enabled) are never sources of truth.
All execution paths call make_pipeline_decision(context).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

DECISION_ENGINE_SOURCE = "PIPELINE_DECISION_ENGINE"
_FALLBACK_SUCCESS_WINDOW_SEC = 3600.0


class PipelineDecisionMode(str, Enum):
    NORMAL = "NORMAL"
    FALLBACK = "FALLBACK"
    MINIMAL = "MINIMAL"
    BLOCKED = "BLOCKED"


class PipelineNextAction(str, Enum):
    SUMMARIZE = "SUMMARIZE"
    SKIP = "SKIP"
    RETRY = "RETRY"
    FORCE_DRAFT = "FORCE_DRAFT"


@dataclass(frozen=True, slots=True)
class PipelineDecisionContext:
    raw_unprocessed: int
    circuit_state: str
    circuit_allows: bool
    openai_status: str
    summarizer_health: str
    fallback_available: bool
    backlog_size: int
    last_successful_tick_sec_ago: float | None
    last_successful_ai_sec_ago: float | None
    retry_pressure: float = 0.0
    system_load: float = 0.0
    force_ai: bool = False
    minimal_mode: bool = False
    fallback_success_recent: bool = False


@dataclass(frozen=True, slots=True)
class PipelineDecision:
    should_execute: bool
    mode: PipelineDecisionMode
    reason: str
    next_action: PipelineNextAction
    observability_trace: dict[str, Any] = field(default_factory=dict)
    ai_gate_open: bool = False
    use_fallback: bool = False
    degraded_observability_only: bool = True

    @property
    def summarize_enabled(self) -> bool:
        return self.next_action in (
            PipelineNextAction.SUMMARIZE,
            PipelineNextAction.FORCE_DRAFT,
            PipelineNextAction.RETRY,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["next_action"] = self.next_action.value
        d["decision_source"] = DECISION_ENGINE_SOURCE
        d["summarize_enabled"] = self.summarize_enabled
        return d


def count_raw_unprocessed_sync() -> int:
    try:
        from utils.database_url import sqlite_path_from_url

        raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
        path = sqlite_path_from_url(raw)
        if not path or not os.path.isfile(path):
            return 0
        conn = sqlite3.connect(path)
        try:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM raw_posts WHERE processed_at IS NULL"
                ).fetchone()[0]
            )
        finally:
            conn.close()
    except Exception:
        return 0


def _reasoning_chain(steps: list[str]) -> list[str]:
    return steps


def make_pipeline_decision(context: PipelineDecisionContext) -> PipelineDecision:
    """
    Deterministic decision from live context. Never reads ai_pipeline_enabled snapshot.
    """
    backlog = max(0, int(context.backlog_size or context.raw_unprocessed or 0))
    chain: list[str] = [f"backlog={backlog}", f"circuit={context.circuit_state}"]

    degraded_obs = context.openai_status != "healthy"
    # DEGRADED never blocks execution when backlog exists.
    if backlog > 0 and degraded_obs:
        chain.append("degraded_observability_only:backlog_present")

    trace_base: dict[str, Any] = {
        "raw_unprocessed": context.raw_unprocessed,
        "backlog_size": backlog,
        "circuit_state": context.circuit_state,
        "circuit_allows": context.circuit_allows,
        "openai_status": context.openai_status,
        "summarizer_health": context.summarizer_health,
        "fallback_available": context.fallback_available,
        "retry_pressure": context.retry_pressure,
        "system_load": context.system_load,
        "reasoning_chain": [],
    }

    if context.minimal_mode:
        chain.append("minimal_mode:force_execution")
        trace_base["reasoning_chain"] = _reasoning_chain(chain)
        return PipelineDecision(
            should_execute=True,
            mode=PipelineDecisionMode.MINIMAL,
            reason="minimal_pipeline_mode",
            next_action=PipelineNextAction.FORCE_DRAFT if backlog > 0 else PipelineNextAction.SUMMARIZE,
            observability_trace=trace_base,
            ai_gate_open=context.circuit_allows,
            use_fallback=backlog > 0 and (not context.circuit_allows or degraded_obs),
            degraded_observability_only=degraded_obs,
        )

    if context.force_ai:
        chain.append("force_ai:full_path")
        trace_base["reasoning_chain"] = _reasoning_chain(chain)
        return PipelineDecision(
            should_execute=True,
            mode=PipelineDecisionMode.NORMAL,
            reason="force_ai_pipeline_enabled",
            next_action=PipelineNextAction.SUMMARIZE,
            observability_trace=trace_base,
            ai_gate_open=True,
            use_fallback=False,
            degraded_observability_only=degraded_obs,
        )

    # Phase 7: backlog MUST trigger action — never BLOCKED due to DEGRADED alone.
    if backlog > 0:
        if context.circuit_allows and not degraded_obs:
            chain.append("backlog:normal_openai")
            trace_base["reasoning_chain"] = _reasoning_chain(chain)
            return PipelineDecision(
                should_execute=True,
                mode=PipelineDecisionMode.NORMAL,
                reason="backlog_execute_normal",
                next_action=PipelineNextAction.SUMMARIZE,
                observability_trace=trace_base,
                ai_gate_open=True,
                use_fallback=False,
                degraded_observability_only=False,
            )
        chain.append("backlog:fallback_required")
        trace_base["reasoning_chain"] = _reasoning_chain(chain)
        return PipelineDecision(
            should_execute=True,
            mode=PipelineDecisionMode.FALLBACK,
            reason="backlog_execute_fallback",
            next_action=PipelineNextAction.SUMMARIZE,
            observability_trace=trace_base,
            ai_gate_open=False,
            use_fallback=True,
            degraded_observability_only=degraded_obs,
        )

    if context.fallback_success_recent and context.circuit_allows:
        chain.append("idle:recent_success")
        trace_base["reasoning_chain"] = _reasoning_chain(chain)
        return PipelineDecision(
            should_execute=True,
            mode=PipelineDecisionMode.NORMAL,
            reason="recent_success_circuit_closed",
            next_action=PipelineNextAction.SUMMARIZE,
            observability_trace=trace_base,
            ai_gate_open=True,
            use_fallback=False,
            degraded_observability_only=degraded_obs,
        )

    if context.circuit_allows and not degraded_obs:
        chain.append("idle:circuit_ok")
        trace_base["reasoning_chain"] = _reasoning_chain(chain)
        return PipelineDecision(
            should_execute=True,
            mode=PipelineDecisionMode.NORMAL,
            reason="idle_ready",
            next_action=PipelineNextAction.SUMMARIZE,
            observability_trace=trace_base,
            ai_gate_open=True,
            use_fallback=False,
            degraded_observability_only=False,
        )

    if not context.circuit_allows:
        chain.append("blocked:circuit_open_no_backlog")
        trace_base["reasoning_chain"] = _reasoning_chain(chain)
        return PipelineDecision(
            should_execute=False,
            mode=PipelineDecisionMode.BLOCKED,
            reason="circuit_open_no_backlog",
            next_action=PipelineNextAction.RETRY,
            observability_trace=trace_base,
            ai_gate_open=False,
            use_fallback=context.fallback_available,
            degraded_observability_only=degraded_obs,
        )

    chain.append("skip:idle_no_backlog")
    trace_base["reasoning_chain"] = _reasoning_chain(chain)
    return PipelineDecision(
        should_execute=False,
        mode=PipelineDecisionMode.BLOCKED,
        reason="idle_no_backlog",
        next_action=PipelineNextAction.SKIP,
        observability_trace=trace_base,
        ai_gate_open=False,
        use_fallback=context.fallback_available,
        degraded_observability_only=degraded_obs,
    )


def log_pipeline_decision_trace(
    context: PipelineDecisionContext,
    decision: PipelineDecision,
    *,
    source: str,
    final_action: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    log_event(
        logger,
        "PIPELINE_DECISION_TRACE",
        source=source,
        decision_source=DECISION_ENGINE_SOURCE,
        context_snapshot=decision.observability_trace,
        should_execute=decision.should_execute,
        mode=decision.mode.value,
        next_action=decision.next_action.value,
        reason=decision.reason,
        ai_gate_open=decision.ai_gate_open,
        use_fallback=decision.use_fallback,
        degraded_observability_only=decision.degraded_observability_only,
        final_action_executed=final_action,
        extra=extra or {},
    )


def apply_pipeline_decision(
    ctx: Any | None = None,
    *,
    source: str,
    context: PipelineDecisionContext | None = None,
) -> PipelineDecision:
    """Single decision point: build context → decide → trace → attach to ctx."""
    if context is None:
        from app.recovery.pipeline_context_builder import build_pipeline_decision_context

        context = build_pipeline_decision_context()
    decision = make_pipeline_decision(context)
    log_pipeline_decision_trace(context, decision, source=source)
    if ctx is not None:
        ctx.pipeline_decision = decision
        # Deprecated mirror for legacy readers — not authoritative.
        ctx.ai_pipeline_enabled = decision.should_execute
        ctx.pipeline_execution = _legacy_adapter(decision)
    _mirror_health_cache(decision)
    return decision


def _mirror_health_cache(decision: PipelineDecision) -> None:
    """Non-authoritative /health mirror only."""
    try:
        from app.dependency_state import get_dependency_state

        deps = get_dependency_state()
        deps.ai_pipeline_enabled = decision.should_execute
        deps._pipeline_decision_cache = decision  # type: ignore[attr-defined]
        deps._pipeline_execution_cache = _legacy_adapter(decision)  # type: ignore[attr-defined]
    except Exception:
        pass


def _legacy_adapter(decision: PipelineDecision) -> Any:
    """Map to PipelineExecutionDecision for transitional imports."""
    from app.state.pipeline_state_engine import (
        PipelineExecutionDecision,
        PipelineExecutionMode,
    )

    mode_map = {
        PipelineDecisionMode.NORMAL: PipelineExecutionMode.ACTIVE,
        PipelineDecisionMode.FALLBACK: PipelineExecutionMode.FALLBACK_BACKLOG,
        PipelineDecisionMode.MINIMAL: PipelineExecutionMode.MINIMAL,
        PipelineDecisionMode.BLOCKED: PipelineExecutionMode.BLOCKED_CIRCUIT,
    }
    return PipelineExecutionDecision(
        execution_active=decision.should_execute,
        summarize_enabled=decision.summarize_enabled,
        ai_gate_open=decision.ai_gate_open,
        use_fallback=decision.use_fallback,
        mode=mode_map.get(decision.mode, PipelineExecutionMode.IDLE),
        reason=decision.reason,
        observability_openai=str(
            decision.observability_trace.get("openai_status", "unknown")
        ),
        degraded_blocks_execution=False,
    )


def should_execute_pipeline(context: PipelineDecisionContext | None = None) -> bool:
    if context is None:
        from app.recovery.pipeline_context_builder import build_pipeline_decision_context

        context = build_pipeline_decision_context()
    return make_pipeline_decision(context).should_execute


def latest_pipeline_decision() -> PipelineDecision | None:
    try:
        from app.dependency_state import get_dependency_state

        return getattr(get_dependency_state(), "_pipeline_decision_cache", None)
    except Exception:
        return None
