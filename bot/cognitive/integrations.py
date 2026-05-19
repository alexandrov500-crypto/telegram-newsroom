from __future__ import annotations

from bot.cognitive.routing import AdaptiveModelRouter
from bot.cognitive.types import CognitiveContext, RouteDecision

_active_router: AdaptiveModelRouter | None = None


def set_active_router(router: AdaptiveModelRouter | None) -> None:
    global _active_router
    _active_router = router


def get_active_router() -> AdaptiveModelRouter | None:
    return _active_router


def route_for_operation(
    operation: str,
    *,
    importance_score: float = 0.5,
    qos_class: str = "standard",
    degradation_mode: str = "normal",
    latency_pressure: float = 0.0,
    **extra: object,
) -> RouteDecision | None:
    """Optional hook for processing modules; returns None if cognitive runtime inactive."""
    router = _active_router
    if router is None:
        return None
    ctx = CognitiveContext(
        importance_score=importance_score,
        qos_class=qos_class,
        degradation_mode=degradation_mode,
        latency_pressure=latency_pressure,
        operation=operation,
        extra=dict(extra),
    )
    return router.route(ctx)
