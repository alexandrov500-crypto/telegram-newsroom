"""Compatibility shim — decisions delegated to pipeline_decision_engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.state.pipeline_decision_engine import (
    DECISION_ENGINE_SOURCE as DECISION_SOURCE,
    PipelineDecision,
    PipelineDecisionContext,
    apply_pipeline_decision,
    count_raw_unprocessed_sync,
    log_pipeline_decision_trace,
    make_pipeline_decision,
    should_execute_pipeline,
)

PipelineStateContext = PipelineDecisionContext


class PipelineExecutionMode(str, Enum):
    ACTIVE = "active"
    FALLBACK_BACKLOG = "fallback_backlog"
    FORCED = "forced"
    MINIMAL = "minimal"
    IDLE = "idle"
    BLOCKED_CIRCUIT = "blocked_circuit"


@dataclass(frozen=True, slots=True)
class PipelineExecutionDecision:
    execution_active: bool
    summarize_enabled: bool
    ai_gate_open: bool
    use_fallback: bool
    mode: PipelineExecutionMode
    reason: str
    observability_openai: str
    degraded_blocks_execution: bool

    @property
    def ai_pipeline_enabled_derived(self) -> bool:
        return self.execution_active

    def is_active(self) -> bool:
        return self.execution_active

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_active": self.execution_active,
            "summarize_enabled": self.summarize_enabled,
            "mode": self.mode.value,
            "reason": self.reason,
            "decision_source": DECISION_SOURCE,
        }


def _adapter(d: PipelineDecision) -> PipelineExecutionDecision:
    mode_map = {
        "NORMAL": PipelineExecutionMode.ACTIVE,
        "FALLBACK": PipelineExecutionMode.FALLBACK_BACKLOG,
        "MINIMAL": PipelineExecutionMode.MINIMAL,
        "BLOCKED": PipelineExecutionMode.BLOCKED_CIRCUIT,
    }
    return PipelineExecutionDecision(
        execution_active=d.should_execute,
        summarize_enabled=d.summarize_enabled,
        ai_gate_open=d.ai_gate_open,
        use_fallback=d.use_fallback,
        mode=mode_map.get(d.mode.value, PipelineExecutionMode.IDLE),
        reason=d.reason,
        observability_openai=str(d.observability_trace.get("openai_status", "")),
        degraded_blocks_execution=False,
    )


def build_pipeline_state_context(*, raw_unprocessed: int | None = None) -> PipelineDecisionContext:
    from app.recovery.pipeline_context_builder import build_pipeline_decision_context

    return build_pipeline_decision_context(raw_unprocessed=raw_unprocessed)


def evaluate_pipeline_state(context: PipelineDecisionContext) -> PipelineExecutionDecision:
    return _adapter(make_pipeline_decision(context))


def should_run_pipeline(context: PipelineDecisionContext | None = None) -> bool:
    return should_execute_pipeline(context)


def should_run_summarize(context: PipelineDecisionContext | None = None) -> bool:
    from app.recovery.pipeline_context_builder import build_pipeline_decision_context

    ctx = context or build_pipeline_decision_context()
    return make_pipeline_decision(ctx).summarize_enabled


def sync_execution_cache(decision: PipelineExecutionDecision, *, source: str) -> None:
    from app.state.pipeline_decision_engine import _mirror_health_cache
    from app.state.pipeline_decision_engine import (
        PipelineDecisionMode,
        PipelineNextAction,
    )

    mode = PipelineDecisionMode.FALLBACK if decision.use_fallback else PipelineDecisionMode.NORMAL
    if decision.mode == PipelineExecutionMode.MINIMAL:
        mode = PipelineDecisionMode.MINIMAL
    d = PipelineDecision(
        should_execute=decision.execution_active,
        mode=mode,
        reason=decision.reason,
        next_action=(
            PipelineNextAction.SUMMARIZE if decision.summarize_enabled else PipelineNextAction.SKIP
        ),
        ai_gate_open=decision.ai_gate_open,
        use_fallback=decision.use_fallback,
    )
    _mirror_health_cache(d)


def ensure_pipeline_execution_ready(
    ctx: Any | None = None,
    *,
    source: str,
    raw_unprocessed: int | None = None,
) -> PipelineExecutionDecision:
    from app.recovery.pipeline_context_builder import build_pipeline_decision_context

    context = build_pipeline_decision_context(raw_unprocessed=raw_unprocessed)
    return _adapter(apply_pipeline_decision(ctx, source=source, context=context))


def derived_ai_pipeline_enabled() -> bool:
    return should_execute_pipeline()


def get_cached_execution_decision() -> PipelineExecutionDecision | None:
    from app.state.pipeline_decision_engine import latest_pipeline_decision

    d = latest_pipeline_decision()
    return _adapter(d) if d else None
