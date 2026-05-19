from __future__ import annotations

from typing import Any

from bot.ops_resilience.types import DependencyHealthBand, OperationalPosture


def resolve_posture(
    *,
    dependencies: dict[str, dict[str, Any]],
    failure_budgets: dict[str, Any],
    recovery_quality: dict[str, Any],
    soft_degraded: bool,
) -> tuple[str, str]:
    """Determine operational posture and human-readable reason."""
    critical_deps = [
        d
        for d, info in dependencies.items()
        if info.get("band") == DependencyHealthBand.CRITICAL.value
    ]
    unstable_deps = [
        d
        for d, info in dependencies.items()
        if info.get("band") in (
            DependencyHealthBand.UNSTABLE.value,
            DependencyHealthBand.CRITICAL.value,
        )
    ]

    if failure_budgets.get("recovery_storm") or recovery_quality.get("recovery_storm"):
        return (
            OperationalPosture.RECOVERY.value,
            "recovery storm detected — limiting non-critical work",
        )

    if critical_deps or failure_budgets.get("instability_ratio", 0) >= 0.9:
        return (
            OperationalPosture.OBSERVATION_ONLY.value,
            f"critical dependencies: {', '.join(critical_deps[:3]) or 'instability budget'}",
        )

    if soft_degraded or failure_budgets.get("runtime_instability", {}).get("exhausted"):
        return (
            OperationalPosture.PROTECTED.value,
            "runtime pressure — publish and analytics throttled",
        )

    if unstable_deps or failure_budgets.get("alert_volume", {}).get("exhausted"):
        return (
            OperationalPosture.DEGRADED.value,
            f"degraded: {', '.join(unstable_deps[:4]) or 'elevated alerts'}",
        )

    return OperationalPosture.STABLE.value, "all core dependencies within normal bands"
