from __future__ import annotations

from typing import Any

CALM_RECOVERY = "CALM_RECOVERY"
NOISY_RECOVERY = "NOISY_RECOVERY"
MANUAL_STABILIZATION = "MANUAL_STABILIZATION"
CHRONIC_INTERVENTION = "CHRONIC_INTERVENTION"
OSCILLATING_TUNING = "OSCILLATING_TUNING"
NATURAL_RECOVERY = "NATURAL_RECOVERY"


def classify_recovery_archetype(
    *,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recovery pattern label — advisory only, no prediction."""
    gov = governance or {}
    cert = certification or {}
    rehe = rehearsal or {}
    frz = freeze_registry or {}

    calm_band = (rehe.get("recovery_calmness") or {}).get("recovery_calmness_band", "UNEASY")
    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    ledger = frz.get("evolution_ledger") or {}
    volatile = sum(1 for v in ledger.values() if v.get("stability_trend") == "VOLATILE")
    flow = (ctx or {}).get("publish_funnel") or {}
    starve = bool((flow.get("starvation") or {}).get("detected"))
    freeze_break = bool((cert.get("stabilization_freeze") or {}).get("freeze_violations"))

    mode = NATURAL_RECOVERY
    if volatile >= 2 or calm_band == "VOLATILE":
        mode = OSCILLATING_TUNING
    elif chg == "DESTABILIZING" and freeze_break:
        mode = CHRONIC_INTERVENTION
    elif chg in ("ELEVATED", "DESTABILIZING") and freeze_break:
        mode = MANUAL_STABILIZATION
    elif calm_band == "VOLATILE":
        mode = NOISY_RECOVERY
    elif calm_band == "CALM" and not starve:
        mode = CALM_RECOVERY

    improving = calm_band == "CALM" and chg == "LOW" and volatile == 0
    hurting = chg in ("ELEVATED", "DESTABILIZING") or volatile >= 2

    return {
        "historical_recovery_mode": mode,
        "recovery_quality_improving": improving,
        "interventions_likely_hurting": hurting,
        "instability_recurring": volatile >= 2,
    }
