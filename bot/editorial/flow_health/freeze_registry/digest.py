from __future__ import annotations

from typing import Any


def should_ultra_quiet_digest(
    *,
    certification: dict[str, Any] | None = None,
    drift_exposure: dict[str, Any] | None = None,
    horizon: dict[str, Any] | None = None,
    all_calm: bool = False,
) -> bool:
    """Healthy silence — show only meaningful anomalies."""
    cert = certification or {}
    conf_band = (cert.get("operational_confidence") or {}).get("operational_confidence_band")
    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    exp_band = (drift_exposure or {}).get("drift_exposure_band", "CONTROLLED")
    hor_band = (horizon or {}).get("stewardship_horizon_band", "STABLE")
    return (
        all_calm
        and conf_band == "CERTIFIED"
        and chg == "LOW"
        and exp_band == "MINIMAL"
        and hor_band in ("LONG", "AUTONOMOUS_CANDIDATE")
    )


def build_freeze_stewardship_lines(
    *,
    freeze_registry: dict[str, Any] | None = None,
    drift_exposure: dict[str, Any] | None = None,
    horizon: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    evolution_ledger: dict[str, dict[str, Any]] | None = None,
    ultra_quiet: bool = False,
) -> list[str]:
    """Stewardship milestones and churn awareness — compact."""
    lines: list[str] = []
    reg = freeze_registry or {}
    exp = drift_exposure or {}
    hor = horizon or {}
    cert = certification or {}

    if ultra_quiet:
        days = hor.get("stewardship_horizon_days")
        if days:
            lines.append(f"Horizon ~{days}d · {hor.get('stewardship_horizon_band', 'STABLE')}")
        violations = (cert.get("stabilization_freeze") or {}).get("freeze_violations") or []
        if violations:
            lines.append(f"Freeze attention: {', '.join(violations[:2])}")
        if exp.get("drift_exposure_band") not in (None, "MINIMAL"):
            lines.append(f"Drift exposure {exp.get('drift_exposure_band')}")
        return lines[:4]

    if exp.get("drift_exposure_band") not in (None, "MINIMAL"):
        lines.append(
            f"Drift exposure {exp.get('drift_exposure_index')} · {exp.get('drift_exposure_band')}",
        )
    if hor.get("stewardship_horizon_days"):
        lines.append(
            f"Stewardship horizon ~{hor['stewardship_horizon_days']}d ({hor.get('stewardship_horizon_band')})",
        )

    ledger = evolution_ledger or {}
    volatile = [k for k, v in ledger.items() if v.get("stability_trend") == "VOLATILE"][:3]
    if volatile:
        lines.append(f"Active churn: {', '.join(volatile)}")

    calm = [
        k
        for k, v in ledger.items()
        if v.get("stability_trend") == "CALM" and int(v.get("last_modified_days") or 0) >= 14
    ]
    if calm and not volatile:
        lines.append(f"Settled surfaces: {len(calm)} subsystem(s) calm 14d+")

    stab = cert.get("stabilization_freeze") or {}
    if stab.get("freeze_violations"):
        lines.append(f"Freeze violations: {', '.join(stab['freeze_violations'][:2])}")

    imm = len(reg.get("immutable_core") or [])
    if imm:
        lines.append(f"Immutable core: {imm} subsystem(s) (advisory map)")

    return lines[:6]
