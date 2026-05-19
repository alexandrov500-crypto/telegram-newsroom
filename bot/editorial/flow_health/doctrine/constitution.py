from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.doctrine.principles import (
    ADVISORY_OVER_AUTOMATION,
    ALIGNED,
    AT_RISK,
    BOUNDED_COMPLEXITY,
    DETERMINISTIC_PUBLISH_PATH,
    DRIFTING,
    FAIL_OPEN_GOVERNANCE,
    HUMAN_ACCOUNTABLE_EDITORIAL,
    MINIMAL_RUNTIME_SURFACE,
    NO_SELF_MODIFYING_BEHAVIOR,
    OPERATIONAL_CALMNESS,
    QUIET_HEALTHY_OPERATIONS,
    ALL_PRINCIPLES,
)


def build_operational_constitution(
    *,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explicit doctrine registry — advisory alignment only."""
    gov = governance or {}
    cert = certification or {}
    frz = freeze_registry or {}
    omem = operational_memory or {}
    slim = slimming or {}
    rel = reliability or {}
    cockpit = cockpit or {}

    exp_band = (frz.get("drift_exposure") or {}).get("drift_exposure_band", "CONTROLLED")
    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    conf_band = (cert.get("operational_confidence") or {}).get("operational_confidence_band", "PROVISIONAL")
    calm_band = omem.get("institutional_calmness_band", "REACTIVE")
    warn_p = float(cockpit.get("warning_pressure") or 0)
    cfg_band = (slim.get("config_surface") or {}).get("config_complexity_band", "low")
    heuristic_n = int((slim.get("consolidation") or {}).get("heuristic_density") or 0)
    tele_d = float((rel.get("telemetry_density") or {}).get("telemetry_density_score") or 0)
    freeze_ok = (cert.get("stabilization_freeze") or {}).get("stabilization_freeze_status") == "STABLE_FREEZE"
    ultra = bool(frz.get("ultra_quiet_digest"))
    recurrence = bool(omem.get("recurrence_detected"))
    flow = (ctx or {}).get("publish_funnel") or {}

    def _entry(principle: str, status: str, signals: list[str]) -> dict[str, Any]:
        return {"principle": principle, "status": status, "evidence_signals": signals[:4]}

    entries: list[dict[str, Any]] = []

    calm_status = ALIGNED if exp_band == "MINIMAL" and calm_band in ("MATURE", "INSTITUTIONAL") else (
        DRIFTING if exp_band == "FRAGILE" else AT_RISK
    )
    entries.append(
        _entry(
            OPERATIONAL_CALMNESS,
            calm_status,
            [f"drift_exposure_{exp_band}", f"calmness_{calm_band}"],
        ),
    )

    auto_status = ALIGNED if chg == "LOW" and not recurrence else AT_RISK
    if chg == "DESTABILIZING":
        auto_status = DRIFTING
    entries.append(_entry(ADVISORY_OVER_AUTOMATION, auto_status, [f"change_pressure_{chg}"]))

    pub_status = ALIGNED if not (flow.get("starvation") or {}).get("detected") else AT_RISK
    entries.append(_entry(DETERMINISTIC_PUBLISH_PATH, pub_status, ["publish_path_observed"]))

    bound_status = ALIGNED if cfg_band == "low" and heuristic_n < 5 else (
        DRIFTING if heuristic_n >= 6 or cfg_band == "high" else AT_RISK
    )
    entries.append(
        _entry(
            BOUNDED_COMPLEXITY,
            bound_status,
            [f"config_{cfg_band}", f"heuristic_density_{heuristic_n}"],
        ),
    )

    fail_status = ALIGNED if freeze_ok else AT_RISK
    entries.append(_entry(FAIL_OPEN_GOVERNANCE, fail_status, ["freeze_discipline"]))

    human_status = ALIGNED if conf_band in ("TRUSTED", "CERTIFIED") else AT_RISK
    entries.append(_entry(HUMAN_ACCOUNTABLE_EDITORIAL, human_status, [f"confidence_{conf_band}"]))

    surface_status = ALIGNED if tele_d < 0.55 else AT_RISK
    if tele_d >= 0.75:
        surface_status = DRIFTING
    entries.append(_entry(MINIMAL_RUNTIME_SURFACE, surface_status, [f"telemetry_density_{tele_d:.2f}"]))

    quiet_status = ALIGNED if ultra or warn_p < 0.3 else AT_RISK
    if warn_p >= 0.5:
        quiet_status = DRIFTING
    entries.append(_entry(QUIET_HEALTHY_OPERATIONS, quiet_status, [f"warning_pressure_{warn_p:.2f}"]))

    self_status = ALIGNED if chg == "LOW" and not (omem.get("recovery_pattern") or {}).get(
        "interventions_likely_hurting",
    ) else AT_RISK
    entries.append(_entry(NO_SELF_MODIFYING_BEHAVIOR, self_status, ["intervention_dependency"]))

    aligned_n = sum(1 for e in entries if e["status"] == ALIGNED)
    drifting_n = sum(1 for e in entries if e["status"] == DRIFTING)
    if drifting_n >= 2:
        alignment = "DRIFTING"
    elif aligned_n >= len(ALL_PRINCIPLES) - 2:
        alignment = "ALIGNED"
    elif aligned_n >= len(ALL_PRINCIPLES) // 2:
        alignment = "AT_RISK"
    else:
        alignment = "MISALIGNED"

    return {
        "principles": entries,
        "doctrine_alignment_status": alignment,
        "aligned_count": aligned_n,
        "drifting_count": drifting_n,
    }
