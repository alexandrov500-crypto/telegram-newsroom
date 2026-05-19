from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.doctrine.principles import ALIGNED, DRIFTING


def compute_stewardship_constitution(
    *,
    constitution: dict[str, Any] | None = None,
    doctrine_drift: dict[str, Any] | None = None,
    complexity: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Architectural philosophy continuity score — not quality or reliability."""
    const = constitution or {}
    drift = doctrine_drift or {}
    comp = complexity or {}
    cert = certification or {}
    frz = freeze_registry or {}
    omem = operational_memory or {}

    aligned = int(const.get("aligned_count") or 0)
    total = max(1, len(const.get("principles") or []))
    align_ratio = aligned / total

    freeze_ok = (cert.get("stabilization_freeze") or {}).get("stabilization_freeze_status") == "STABLE_FREEZE"
    calm = float(omem.get("institutional_calmness_index") or 0.5)
    exp = float((frz.get("drift_exposure") or {}).get("drift_exposure_index") or 0.25)
    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    ultra = bool(frz.get("ultra_quiet_digest"))
    bounded = bool(comp.get("complexity_bounded"))

    raw = (
        align_ratio * 0.35
        + calm * 0.2
        + (0.12 if freeze_ok else 0)
        + (0.1 if bounded else 0)
        + (0.08 if ultra else 0)
        + (0.08 if chg == "LOW" else 0)
        + (1 - exp) * 0.12
    )
    if drift.get("doctrine_drift_detected"):
        raw -= 0.15
    if int(const.get("drifting_count") or 0) >= 2:
        raw -= 0.1

    score = round(max(0.0, min(1.0, raw)), 3)
    band = "FRAGMENTED"
    if score >= 0.82 and const.get("doctrine_alignment_status") == "ALIGNED":
        band = "CONSTITUTIONAL"
    elif score >= 0.68:
        band = "ALIGNED"
    elif score >= 0.45:
        band = "MISALIGNED"

    return {
        "stewardship_constitution_score": score,
        "stewardship_constitution_band": band,
    }


def evaluate_institutional_stewardship_mode(
    *,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    constitution: dict[str, Any] | None = None,
    stewardship_constitution: dict[str, Any] | None = None,
    complexity: dict[str, Any] | None = None,
    doctrine_drift: dict[str, Any] | None = None,
) -> bool:
    """Long-lived operational infrastructure behavior — advisory flag only."""
    cert = certification or {}
    frz = freeze_registry or {}
    omem = operational_memory or {}
    const = constitution or {}
    stew = stewardship_constitution or {}
    comp = complexity or {}
    drift = doctrine_drift or {}

    conf = (cert.get("operational_confidence") or {}).get("operational_confidence_band")
    exp = (frz.get("drift_exposure") or {}).get("drift_exposure_band")
    calm = omem.get("institutional_calmness_band")
    hor = (frz.get("stewardship_horizon") or {}).get("stewardship_horizon_band")
    align = const.get("doctrine_alignment_status")
    stew_band = stew.get("stewardship_constitution_band")

    return bool(
        conf == "CERTIFIED"
        and exp == "MINIMAL"
        and calm == "INSTITUTIONAL"
        and hor in ("LONG", "AUTONOMOUS_CANDIDATE")
        and align in ("ALIGNED",)
        and stew_band in ("ALIGNED", "CONSTITUTIONAL")
        and comp.get("complexity_bounded")
        and not drift.get("doctrine_drift_detected")
        and not omem.get("recurrence_detected")
    )
