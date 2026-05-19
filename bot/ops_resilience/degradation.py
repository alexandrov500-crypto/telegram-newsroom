from __future__ import annotations

from typing import Any

from bot.ops_resilience.types import DependencyHealthBand


def build_degradation_matrix(
    dependencies: dict[str, dict[str, Any]],
    *,
    pulse: dict[str, Any],
    failure_budgets: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Map conditions to controlled responses (advisory actions applied via context).
    """
    actions: list[dict[str, Any]] = []
    lag = float(pulse.get("event_loop_lag_max") or 0)
    recovery = int(pulse.get("recovery_attempt_count") or 0)

    tg = dependencies.get("telegram_api", {})
    if tg.get("band") in (DependencyHealthBand.DEGRADED.value, DependencyHealthBand.UNSTABLE.value):
        actions.append(
            {
                "condition": "telegram_slow",
                "response": "reduce_publish_attempts",
                "factor": 0.5,
            },
        )
    if tg.get("band") == DependencyHealthBand.CRITICAL.value:
        actions.append(
            {
                "condition": "telegram_critical",
                "response": "observation_only",
            },
        )

    rss = dependencies.get("rss_ingestion", {})
    if rss.get("band") in (
        DependencyHealthBand.DEGRADED.value,
        DependencyHealthBand.UNSTABLE.value,
    ):
        actions.append(
            {
                "condition": "rss_overloaded",
                "response": "ingestion_throttle",
                "multiplier": 3.0,
            },
        )

    sqlite = dependencies.get("sqlite", {})
    if sqlite.get("band") in (
        DependencyHealthBand.DEGRADED.value,
        DependencyHealthBand.UNSTABLE.value,
        DependencyHealthBand.CRITICAL.value,
    ):
        actions.append(
            {
                "condition": "db_contention",
                "response": "defer_non_critical_writes",
            },
        )

    if lag >= 0.4 or pulse.get("stalled_loops"):
        actions.append(
            {
                "condition": "event_loop_lag",
                "response": "pause_background_analytics",
            },
        )

    fs = dependencies.get("filesystem", {})
    if fs.get("band") in (
        DependencyHealthBand.DEGRADED.value,
        DependencyHealthBand.UNSTABLE.value,
        DependencyHealthBand.CRITICAL.value,
    ):
        actions.append(
            {
                "condition": "disk_pressure",
                "response": "suspend_archival",
            },
        )

    if failure_budgets.get("recovery_storm") or recovery > 6:
        actions.append(
            {
                "condition": "repeated_failures",
                "response": "safe_observation_mode",
            },
        )

    if float(failure_budgets.get("instability_ratio") or 0) > 0.7:
        actions.append(
            {
                "condition": "instability_budget_exhausted",
                "response": "pause_background_analytics",
            },
        )

    return actions
