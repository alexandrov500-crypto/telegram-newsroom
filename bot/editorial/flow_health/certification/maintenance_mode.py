from __future__ import annotations

from typing import Any


def validate_maintenance_mode_readiness(
    *,
    rehearsal: dict[str, Any] | None = None,
    stabilization: dict[str, Any] | None = None,
    change_pressure: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Whether newsroom can run with minimal tuning and infrequent review."""
    rehe = rehearsal or {}
    stab = stabilization or {}
    chg = change_pressure or {}
    conf = confidence or {}
    rel = reliability or {}

    maint = rehe.get("maintenance_readiness") or {}
    drift = (rehe.get("drift_boundaries") or {}).get("drift_boundary_status", "WITHIN_BOUNDS")
    uptime = (rehe.get("uptime_stability") or {}).get("uptime_stability_health", "HEALTHY")
    surv_band = (rel.get("survivability") or {}).get("survivability_band", "OK")

    ready = (
        maint.get("maintenance_readiness") == "READY"
        and stab.get("stabilization_freeze_status") == "STABLE_FREEZE"
        and chg.get("change_pressure_band") == "LOW"
        and conf.get("operational_confidence_band") in ("TRUSTED", "CERTIFIED")
        and drift == "WITHIN_BOUNDS"
        and uptime in ("HEALTHY", "WATCH")
        and surv_band != "FRAGILE"
        and not stab.get("freeze_violations")
    )

    blockers = [
        b
        for b, cond in (
            ("maintenance_not_ready", maint.get("maintenance_readiness") != "READY"),
            ("freeze_unstable", stab.get("stabilization_freeze_status") != "STABLE_FREEZE"),
            ("change_pressure_elevated", chg.get("change_pressure_band") != "LOW"),
            ("confidence_low", conf.get("operational_confidence_band") == "PROVISIONAL"),
            ("drift_elevated", drift not in ("WITHIN_BOUNDS",)),
            ("uptime_degraded", uptime == "DEGRADED"),
            ("survivability_fragile", surv_band == "FRAGILE"),
        )
        if cond
    ]

    return {
        "maintenance_mode_ready": ready,
        "maintenance_mode_blockers": blockers,
    }
