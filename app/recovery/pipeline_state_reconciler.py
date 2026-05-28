"""Context builder + health mirror — decisions live in pipeline_decision_engine only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.recovery.pipeline_context_builder import build_pipeline_decision_context
from app.state.pipeline_decision_engine import (
    PipelineDecision,
    apply_pipeline_decision,
    count_raw_unprocessed_sync,
    make_pipeline_decision,
)


@dataclass(frozen=True, slots=True)
class PipelineStateReconcileResult:
    """Legacy shape for tools; values come from PipelineDecision."""

    ai_pipeline_enabled: bool
    summarize_enabled: bool
    pipeline_active: bool
    reconciled: bool
    raw_unprocessed: int
    reason: str
    circuit_state: str
    circuit_allows: bool
    openai_dependency: str


def _to_result(decision: PipelineDecision, context: Any) -> PipelineStateReconcileResult:
    return PipelineStateReconcileResult(
        ai_pipeline_enabled=decision.should_execute,
        summarize_enabled=decision.summarize_enabled,
        pipeline_active=decision.should_execute,
        reconciled=True,
        raw_unprocessed=context.raw_unprocessed,
        reason=decision.reason,
        circuit_state=context.circuit_state,
        circuit_allows=context.circuit_allows,
        openai_dependency=context.openai_status,
    )


def build_pipeline_context_only(*, raw_unprocessed: int | None = None) -> Any:
    """Context only — does not enable/disable pipeline."""
    return build_pipeline_decision_context(raw_unprocessed=raw_unprocessed)


def reconcile_pipeline_state(
    *,
    raw_unprocessed: int | None = None,
    apply: bool = True,
    source: str = "reconciler",
    ctx: Any | None = None,
) -> PipelineStateReconcileResult:
    """Deprecated name: runs decision engine (context → decide → trace)."""
    context = build_pipeline_decision_context(raw_unprocessed=raw_unprocessed)
    if apply:
        decision = apply_pipeline_decision(ctx, source=source, context=context)
    else:
        decision = make_pipeline_decision(context)
    return _to_result(decision, context)


def ensure_pipeline_execution_ready(
    ctx: Any | None = None,
    *,
    source: str,
    raw_unprocessed: int | None = None,
) -> Any:
    """Mandatory pre-execution — delegates to apply_pipeline_decision."""
    context = build_pipeline_decision_context(raw_unprocessed=raw_unprocessed)
    decision = apply_pipeline_decision(ctx, source=source, context=context)
    return decision


def note_successful_summarize_tick(*, draft_created: bool) -> None:
    if not draft_created:
        return
    from app.runtime_activity import record_fallback_success

    record_fallback_success()
    apply_pipeline_decision(source="post_summarize_success")


def reconciliation_health_extra() -> dict[str, Any]:
    context = build_pipeline_decision_context()
    decision = make_pipeline_decision(context)
    return {
        "decision_source": "PIPELINE_DECISION_ENGINE",
        "should_execute": decision.should_execute,
        "summarize_enabled": decision.summarize_enabled,
        "mode": decision.mode.value,
        "next_action": decision.next_action.value,
        "reason": decision.reason,
        "raw_unprocessed": context.raw_unprocessed,
        "use_fallback": decision.use_fallback,
        "observability_trace": decision.observability_trace,
    }


__all__ = [
    "PipelineStateReconcileResult",
    "build_pipeline_context_only",
    "count_raw_unprocessed_sync",
    "reconcile_pipeline_state",
    "note_successful_summarize_tick",
    "reconciliation_health_extra",
    "ensure_pipeline_execution_ready",
]
