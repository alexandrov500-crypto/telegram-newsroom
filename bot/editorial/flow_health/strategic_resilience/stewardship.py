from __future__ import annotations

from typing import Any

def assess_stewardship_fatigue(
    *,
    certification: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    erosion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Intervention churn as long-term fragility source — not operator scoring."""
    cert = certification or {}
    omem = operational_memory or {}
    frz = freeze_registry or {}
    eros = erosion or {}

    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    ledger = frz.get("evolution_ledger") or {}
    volatile = sum(1 for v in ledger.values() if v.get("stability_trend") == "VOLATILE")
    recurrence = bool(omem.get("recurrence_detected"))
    hurting = bool((omem.get("recovery_pattern") or {}).get("interventions_likely_hurting"))

    fatigue = chg in ("ELEVATED", "DESTABILIZING") or volatile >= 2 or recurrence
    rising = chg == "ELEVATED" or volatile >= 1
    stable_recovery = bool(
        (omem.get("recovery_pattern") or {}).get("recovery_quality_improving")
        and not hurting,
    )

    return {
        "stewardship_fatigue_detected": fatigue,
        "intervention_dependency_rising": rising,
        "sustainability_recovery_stable": stable_recovery,
    }


def estimate_sustainability_horizon(
    *,
    resilience: dict[str, Any] | None = None,
    erosion: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    sustainability: dict[str, Any] | None = None,
    fatigue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Architectural integrity horizon — calm heuristic, not prediction engine."""
    res = resilience or {}
    eros = erosion or {}
    doc = doctrine or {}
    omem = operational_memory or {}
    frz = freeze_registry or {}
    sust = sustainability or {}
    fat = fatigue or {}

    index = float(res.get("strategic_resilience_index") or 0.6)
    agg = float(sust.get("sustainability_aggregate") or 0.6)
    erosion_n = len(eros.get("erosion_signals") or [])
    recurrence_n = len((omem.get("recurrence") or {}).get("recurrence_signatures") or [])
    align = doc.get("doctrine_alignment_status", "AT_RISK")
    stew_horizon = int((frz.get("stewardship_horizon") or {}).get("stewardship_horizon_days") or 14)

    days = int(
        index * 45
        + agg * 20
        + stew_horizon * 0.35
        + (12 if align == "ALIGNED" else 0)
        - erosion_n * 6
        - recurrence_n * 4
        - (10 if fat.get("stewardship_fatigue_detected") else 0),
    )
    days = max(3, min(120, days))

    band = "SHORT"
    if days >= 75 and res.get("strategic_resilience_band") == "LONG_HORIZON":
        band = "INSTITUTIONAL_LONG_HORIZON"
    elif days >= 45:
        band = "LONG"
    elif days >= 21:
        band = "MAINTAINED"

    return {
        "sustainability_horizon_days": days,
        "sustainability_horizon_band": band,
    }


def evaluate_long_horizon_sustainability(
    *,
    resilience: dict[str, Any] | None = None,
    horizon: dict[str, Any] | None = None,
    erosion: dict[str, Any] | None = None,
    fatigue: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
) -> bool:
    """Infrastructure can sustain calmness over months — advisory flag."""
    res = resilience or {}
    hor = horizon or {}
    eros = erosion or {}
    fat = fatigue or {}
    doc = doctrine or {}

    return bool(
        res.get("strategic_resilience_band") in ("RESILIENT", "LONG_HORIZON")
        and hor.get("sustainability_horizon_band") in ("LONG", "INSTITUTIONAL_LONG_HORIZON")
        and not eros.get("architectural_erosion_detected")
        and not fat.get("stewardship_fatigue_detected")
        and doc.get("doctrine_alignment_status") in ("ALIGNED",)
        and not doc.get("doctrine_drift_detected"),
    )
