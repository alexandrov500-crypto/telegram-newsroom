from __future__ import annotations

from typing import Any


def build_observability_digest_lines(
    *,
    cohesion: dict[str, Any] | None = None,
    integrity: dict[str, Any] | None = None,
    drift: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    canonical_quiet: bool = False,
) -> list[str]:
    """Max 1 line when canonical — no observability dashboard."""
    if canonical_quiet and not drift.get("observability_drift_detected"):
        streak = int((continuity or {}).get("canonical_truth_streak_days") or 0)
        if streak >= 7:
            return ["Operational observability remains canonically coherent"]
        return ["Governance propagation remains internally consistent"]

    if drift.get("observability_drift_detected"):
        sig = (drift.get("observability_drift_signals") or ["observability drift"])[0]
        if "stale_read" in sig:
            return ["Collector telemetry diverges from canonical governance snapshot"]
        return [f"Observability drift: {sig.replace('_', ' ')[:80]}"]

    if cohesion.get("governance_cohesion_status") == "FRAGMENTED":
        return ["Governance cohesion fragmented across stewardship layers"]

    return []
