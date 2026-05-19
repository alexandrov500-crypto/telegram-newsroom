from __future__ import annotations

from bot.signals.types import ImpactProfile, TrendForecast


def forecast_escalation(
    *,
    story_id: int | None,
    importance: float,
    trend_velocity: float,
    source_count: int,
    novelty: float,
    impact: ImpactProfile,
    correlation_velocity: float = 0.0,
) -> TrendForecast:
    """Heuristic escalation forecast from momentum signals."""
    momentum = (
        importance * 0.28
        + trend_velocity * 0.24
        + min(1.0, source_count / 5.0) * 0.18
        + novelty * 0.12
        + impact.composite * 0.12
        + correlation_velocity * 0.06
    )
    probability = max(0.0, min(0.98, momentum))
    expected_impact = impact.composite
    expected_reach = min(
        1.0,
        trend_velocity * 0.4 + min(1.0, source_count / 6.0) * 0.35 + probability * 0.25,
    )
    return TrendForecast(
        forecast_probability=probability,
        expected_impact=expected_impact,
        expected_reach=expected_reach,
        story_id=story_id,
    )
