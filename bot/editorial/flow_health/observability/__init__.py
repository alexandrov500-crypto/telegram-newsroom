from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.observability.cohesion import assess_governance_cohesion
from bot.editorial.flow_health.observability.consistency import detect_observability_drift
from bot.editorial.flow_health.observability.continuity import (
    is_canonical_truth_day,
    touch_canonical_truth_continuity,
)
from bot.editorial.flow_health.observability.digest import build_observability_digest_lines
from bot.editorial.flow_health.observability.integrity import compute_observability_integrity
from bot.editorial.flow_health.observability.propagation import verify_canonical_propagation


def observability_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    collector_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Observability integrity & governance cohesion — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    coll = collector_ctx or ctx or {}

    propagation = verify_canonical_propagation(
        enriched_governance=gov,
        collector_ctx=coll,
    )
    cohesion = assess_governance_cohesion(governance=gov, propagation=propagation)
    drift = detect_observability_drift(
        governance=gov,
        cohesion=cohesion,
        propagation=propagation,
    )
    integrity = compute_observability_integrity(
        cohesion=cohesion,
        propagation=propagation,
        drift=drift,
        governance=gov,
    )
    coherent = is_canonical_truth_day(
        cohesion=cohesion,
        integrity=integrity,
        propagation=propagation,
        drift=drift,
    )
    continuity = touch_canonical_truth_continuity(coherent_today=coherent)

    clos = gov.get("closure") or {}
    min_g = gov.get("minimalism") or {}
    canonical_quiet = bool(
        cohesion.get("governance_cohesion_status") in ("COHERENT", "CANONICAL")
        and integrity.get("observability_integrity_band") in ("STABLE", "CANONICAL")
        and min_g.get("invisible_digest_mode")
        and clos.get("operational_closure_candidate")
        and not drift.get("observability_drift_detected")
    )

    digest_lines = build_observability_digest_lines(
        cohesion=cohesion,
        integrity=integrity,
        drift=drift,
        continuity=continuity,
        canonical_quiet=canonical_quiet,
    )

    return {
        "propagation": propagation,
        "cohesion": cohesion,
        "governance_cohesion_status": cohesion.get("governance_cohesion_status"),
        "integrity": integrity,
        "observability_integrity_index": integrity.get("observability_integrity_index"),
        "observability_integrity_band": integrity.get("observability_integrity_band"),
        "drift": drift,
        "observability_drift_detected": drift.get("observability_drift_detected"),
        "continuity": continuity,
        "canonical_truth_streak_days": continuity.get("canonical_truth_streak_days"),
        "observability_digest_lines": digest_lines,
        "canonical_observability_quiet": canonical_quiet,
    }


__all__ = ["observability_snapshot"]
