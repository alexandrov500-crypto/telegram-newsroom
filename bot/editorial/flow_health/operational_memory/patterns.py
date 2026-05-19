from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.operational_memory.signatures import (
    CALM_CERTIFIED_WINDOW,
    CHANGE_PRESSURE_SPIKE,
    FREEZE_DISCIPLINE_BREAK,
    VOLATILE_TUNING_PERIOD,
)


def compute_institutional_calmness(
    *,
    operational_memory: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Historical operational maturity — not uptime, not reliability."""
    mem = operational_memory or {}
    incidents: list[dict[str, Any]] = list(mem.get("incidents") or [])
    cert = certification or {}
    frz = freeze_registry or {}
    rel = reliability or {}

    calm_resolved = sum(
        1 for i in incidents if i.get("resolved") and i.get("resolution_mode") == "CALM_RECOVERY"
    )
    destabilizing = sum(
        1
        for i in incidents
        if i.get("signature")
        in (
            CHANGE_PRESSURE_SPIKE,
            VOLATILE_TUNING_PERIOD,
            FREEZE_DISCIPLINE_BREAK,
        )
        and int(i.get("occurrences") or 0) >= 2
    )
    total = max(1, len(incidents))
    calm_ratio = calm_resolved / total
    destab_penalty = min(0.35, destabilizing * 0.08)

    freeze_ok = (cert.get("stabilization_freeze") or {}).get("stabilization_freeze_status") == "STABLE_FREEZE"
    exp = float((frz.get("drift_exposure") or {}).get("drift_exposure_index") or 0.25)
    ledger = frz.get("evolution_ledger") or {}
    volatile_n = sum(1 for v in ledger.values() if v.get("stability_trend") == "VOLATILE")
    surv = float((rel.get("survivability") or {}).get("survivability_score") or 0.7)

    raw = (
        calm_ratio * 0.35
        + (0.15 if freeze_ok else 0)
        + (1 - exp) * 0.2
        + surv * 0.15
        + max(0, 0.15 - volatile_n * 0.05)
        - destab_penalty
    )
    index = round(max(0.0, min(1.0, raw)), 3)

    band = "REACTIVE"
    if index >= 0.78 and destabilizing <= 1:
        band = "INSTITUTIONAL"
    elif index >= 0.62:
        band = "MATURE"
    elif index >= 0.42:
        band = "STABILIZING"

    return {
        "institutional_calmness_index": index,
        "institutional_calmness_band": band,
    }


def detect_recurrence(
    *,
    active_signatures: list[str],
    operational_memory: dict[str, Any] | None = None,
    recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lightweight historical comparison — advisory lines only."""
    mem = operational_memory or {}
    incidents: list[dict[str, Any]] = list(mem.get("incidents") or [])
    lines: list[str] = []
    matched: list[str] = []

    for sig in active_signatures:
        prior = [i for i in incidents if i.get("signature") == sig]
        if not prior:
            continue
        inc = prior[0]
        occ = int(inc.get("occurrences") or 1)
        if occ < 2 and inc.get("last_seen_days", 0) > 14:
            continue
        matched.append(sig)
        if sig == VOLATILE_TUNING_PERIOD:
            lines.append("Current instability resembles prior VOLATILE_TUNING period")
        elif sig == CHANGE_PRESSURE_SPIKE:
            days = int(inc.get("first_seen_days") or 0) - int(inc.get("last_seen_days") or 0)
            est = max(7, abs(days) or 14)
            lines.append(
                f"Exposure spike resembles prior stabilization event (~{est}d recovery historically)",
            )
        elif sig == FREEZE_DISCIPLINE_BREAK:
            lines.append("Repeated freeze discipline degradation detected in memory")
        elif inc.get("resolved") and inc.get("resolution_mode") == "CALM_RECOVERY":
            lines.append(f"Prior {sig} historically resolved with calm recovery")
        else:
            lines.append(f"Pattern {sig} seen {occ} time(s) before (last {inc.get('last_seen_days')}d ago)")

    rec = recovery or {}
    if rec.get("recovery_quality_improving") and CALM_CERTIFIED_WINDOW in active_signatures:
        lines.append("Recovery quality improving vs prior calm windows")

    return {
        "recurrence_detected": bool(matched),
        "recurrence_signatures": matched,
        "recurrence_advisory_lines": lines[:4],
    }
