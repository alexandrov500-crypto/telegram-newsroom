"""Build PipelineDecisionContext only — no execution decisions."""

from __future__ import annotations

from app.state.pipeline_decision_engine import (
    PipelineDecisionContext,
    count_raw_unprocessed_sync,
)

_FALLBACK_SUCCESS_WINDOW_SEC = 3600.0


def _retry_pressure() -> float:
    try:
        from app.runtime_activity import exception_count_in_window

        return min(1.0, exception_count_in_window(600.0) / 10.0)
    except Exception:
        return 0.0


def _system_load() -> float:
    try:
        from utils.metrics import export_snapshot

        gauges = export_snapshot().get("gauges") or {}
        depth = float(gauges.get("queue_depth", 0) or 0)
        return min(1.0, depth / 512.0)
    except Exception:
        return 0.0


def build_pipeline_decision_context(*, raw_unprocessed: int | None = None) -> PipelineDecisionContext:
    from app.dependency_state import get_dependency_state
    from app.openai_circuit import get_openai_circuit
    from app.recovery.pipeline_overrides import is_force_ai_pipeline_enabled, is_minimal_pipeline_mode
    from app.runtime_activity import activity_snapshot, seconds_since_ai

    deps = get_dependency_state()
    circuit = get_openai_circuit()
    snap = circuit.snapshot()
    circuit_state = str(snap.get("state") or "unknown")
    circuit_allows = circuit.allow_request()

    if raw_unprocessed is None:
        raw_unprocessed = count_raw_unprocessed_sync()

    since_ai = seconds_since_ai()
    activity = activity_snapshot()
    since_tick = activity.get("seconds_since_scheduler_tick")
    fallback_recent = since_ai is not None and since_ai <= _FALLBACK_SUCCESS_WINDOW_SEC

    openai_st = deps.openai.status.value
    summarizer_health = "healthy" if circuit_allows and openai_st == "healthy" else "degraded"

    return PipelineDecisionContext(
        raw_unprocessed=raw_unprocessed,
        circuit_state=circuit_state,
        circuit_allows=circuit_allows,
        openai_status=openai_st,
        summarizer_health=summarizer_health,
        fallback_available=True,
        backlog_size=raw_unprocessed,
        last_successful_tick_sec_ago=float(since_tick) if since_tick is not None else None,
        last_successful_ai_sec_ago=since_ai,
        retry_pressure=_retry_pressure(),
        system_load=_system_load(),
        force_ai=is_force_ai_pipeline_enabled(),
        minimal_mode=is_minimal_pipeline_mode(),
        fallback_success_recent=fallback_recent,
    )
