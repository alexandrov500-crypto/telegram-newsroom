from __future__ import annotations

from typing import Any

from bot.ops_resilience.context import ResilienceContext, get_resilience_context


def apply_backpressure(
    degradation_actions: list[dict[str, Any]],
    *,
    posture: str,
) -> dict[str, Any]:
    """Apply load-shedding flags to in-process context."""
    ctx = get_resilience_context()
    ctx.posture = posture
    ctx.reduce_publish_attempts = 1.0
    ctx.ingestion_throttle_multiplier = 1.0
    ctx.defer_non_critical_writes = False
    ctx.pause_background_analytics = False
    ctx.suspend_archival = False
    ctx.observation_only = False
    ctx.active_actions = []

    for action in degradation_actions:
        resp = action.get("response")
        ctx.active_actions.append(str(action.get("condition", resp)))
        if resp == "reduce_publish_attempts":
            ctx.reduce_publish_attempts = min(
                ctx.reduce_publish_attempts,
                float(action.get("factor", 0.5)),
            )
        elif resp == "ingestion_throttle":
            ctx.ingestion_throttle_multiplier = max(
                ctx.ingestion_throttle_multiplier,
                float(action.get("multiplier", 2.0)),
            )
        elif resp == "defer_non_critical_writes":
            ctx.defer_non_critical_writes = True
        elif resp == "pause_background_analytics":
            ctx.pause_background_analytics = True
        elif resp == "suspend_archival":
            ctx.suspend_archival = True
        elif resp in ("observation_only", "safe_observation_mode"):
            ctx.observation_only = True
            ctx.reduce_publish_attempts = min(ctx.reduce_publish_attempts, 0.25)
            ctx.pause_background_analytics = True

    if posture in ("protected", "observation_only"):
        ctx.reduce_publish_attempts = min(ctx.reduce_publish_attempts, 0.5)
    if posture == "observation_only":
        ctx.observation_only = True
        ctx.reduce_publish_attempts = min(ctx.reduce_publish_attempts, 0.0)

    from datetime import datetime, timezone

    ctx.last_updated = datetime.now(timezone.utc).isoformat()

    _sync_runtime_state(ctx)

    return {
        "applied": ctx.to_dict(),
        "shedding": {
            "publish_multiplier": ctx.reduce_publish_attempts,
            "ingestion_multiplier": ctx.ingestion_throttle_multiplier,
            "analytics_deferred": ctx.pause_background_analytics,
            "archival_suspended": ctx.suspend_archival,
        },
    }


def _sync_runtime_state(ctx: ResilienceContext) -> None:
    """Align existing runtime_state flags without overriding operator freeze."""
    try:
        from bot.runtime.state import runtime_state

        runtime_state.operational_mode = ctx.posture
        if ctx.ingestion_throttle_multiplier > 1.0:
            runtime_state.ingestion_interval_multiplier = max(
                runtime_state.ingestion_interval_multiplier,
                ctx.ingestion_throttle_multiplier,
            )
        if ctx.pause_background_analytics or ctx.observation_only:
            runtime_state.autonomous_passive = True
    except Exception:
        pass
