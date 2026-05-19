from __future__ import annotations

from typing import Any

HIGH_WARNING_DENSITY = "HIGH_WARNING_DENSITY"
CHANGE_PRESSURE_SPIKE = "CHANGE_PRESSURE_SPIKE"
DEGRADED_RECOVERY_LOOP = "DEGRADED_RECOVERY_LOOP"
RECOVERY_WITHOUT_STARVATION = "RECOVERY_WITHOUT_STARVATION"
CALM_CERTIFIED_WINDOW = "CALM_CERTIFIED_WINDOW"
VOLATILE_TUNING_PERIOD = "VOLATILE_TUNING_PERIOD"
FREEZE_DISCIPLINE_BREAK = "FREEZE_DISCIPLINE_BREAK"
DRIFT_EXPOSURE_ELEVATED = "DRIFT_EXPOSURE_ELEVATED"


def detect_operational_signatures(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> list[str]:
    """Deterministic compact operational state signatures."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    cert = certification or gov.get("certification") or {}
    rehe = rehearsal or gov.get("rehearsal") or {}
    frz = freeze_registry or gov.get("freeze_registry") or {}
    cockpit = cockpit or gov.get("cockpit") or {}

    active: list[str] = []
    warn_p = float(cockpit.get("warning_pressure") or 0)
    if warn_p >= 0.45 or len(cockpit.get("active_warnings") or []) >= 6:
        active.append(HIGH_WARNING_DENSITY)

    chg = cert.get("change_pressure") or {}
    if chg.get("change_pressure_band") in ("ELEVATED", "DESTABILIZING"):
        active.append(CHANGE_PRESSURE_SPIKE)

    calm = rehe.get("recovery_calmness") or {}
    if calm.get("recovery_calmness_band") == "VOLATILE":
        active.append(DEGRADED_RECOVERY_LOOP)
    elif calm.get("recovery_calmness_band") == "CALM":
        flow = (ctx or {}).get("publish_funnel") or {}
        if not (flow.get("starvation") or {}).get("detected"):
            active.append(RECOVERY_WITHOUT_STARVATION)

    conf = cert.get("operational_confidence") or {}
    if (
        conf.get("operational_confidence_band") == "CERTIFIED"
        and str((gov.get("degradation") or {}).get("mode", "NORMAL")) == "NORMAL"
        and (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY"
    ):
        active.append(CALM_CERTIFIED_WINDOW)

    ledger = frz.get("evolution_ledger") or {}
    if any(v.get("stability_trend") == "VOLATILE" for v in ledger.values()):
        active.append(VOLATILE_TUNING_PERIOD)

    stab = cert.get("stabilization_freeze") or {}
    if stab.get("freeze_violations"):
        active.append(FREEZE_DISCIPLINE_BREAK)

    exp = frz.get("drift_exposure") or {}
    if exp.get("drift_exposure_band") in ("ELEVATED", "FRAGILE"):
        active.append(DRIFT_EXPOSURE_ELEVATED)

    return active
