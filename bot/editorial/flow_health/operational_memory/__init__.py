from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.operational_memory.digest import build_memory_stewardship_lines
from bot.editorial.flow_health.operational_memory.incidents import touch_incident_memory
from bot.editorial.flow_health.operational_memory.patterns import (
    compute_institutional_calmness,
    detect_recurrence,
)
from bot.editorial.flow_health.operational_memory.recoveries import (
    CALM_RECOVERY,
    classify_recovery_archetype,
)
from bot.editorial.flow_health.operational_memory.signatures import detect_operational_signatures


def operational_memory_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational memory & institutional knowledge — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    cert = certification or gov.get("certification") or {}
    rehe = rehearsal or gov.get("rehearsal") or {}
    frz = freeze_registry or gov.get("freeze_registry") or {}
    rel = reliability or gov.get("reliability") or {}
    cockpit = cockpit or gov.get("cockpit") or {}

    signatures = detect_operational_signatures(
        ctx=ctx,
        governance=gov,
        certification=cert,
        rehearsal=rehe,
        freeze_registry=frz,
        cockpit=cockpit,
    )
    recovery = classify_recovery_archetype(
        governance=gov,
        certification=cert,
        rehearsal=rehe,
        freeze_registry=frz,
        ctx=ctx,
    )
    mem = touch_incident_memory(
        signatures=signatures,
        recovery_mode=str(recovery.get("historical_recovery_mode", CALM_RECOVERY)),
        resolved=bool(
            recovery.get("recovery_quality_improving")
            and str((gov.get("degradation") or {}).get("mode", "NORMAL")) == "NORMAL"
        ),
    )
    calmness = compute_institutional_calmness(
        operational_memory=mem,
        certification=cert,
        freeze_registry=frz,
        reliability=rel,
    )
    recurrence = detect_recurrence(
        active_signatures=signatures,
        operational_memory=mem,
        recovery=recovery,
    )

    all_calm = (
        str((gov.get("degradation") or {}).get("mode", "NORMAL")) == "NORMAL"
        and (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY"
    )
    ultra = bool(frz.get("ultra_quiet_digest"))
    memory_lines = build_memory_stewardship_lines(
        calmness=calmness,
        recurrence=recurrence,
        recovery=recovery,
        ultra_quiet=ultra,
        all_calm=all_calm,
    )

    return {
        "active_signatures": signatures,
        "operational_memory": mem,
        "recovery_pattern": recovery,
        "institutional_calmness": calmness,
        "recurrence": recurrence,
        "operational_memory_active": bool(mem.get("incidents")),
        "institutional_calmness_index": calmness.get("institutional_calmness_index"),
        "institutional_calmness_band": calmness.get("institutional_calmness_band"),
        "recurrence_detected": recurrence.get("recurrence_detected"),
        "historical_recovery_mode": recovery.get("historical_recovery_mode"),
        "memory_stewardship_lines": memory_lines,
    }


__all__ = ["operational_memory_snapshot"]
