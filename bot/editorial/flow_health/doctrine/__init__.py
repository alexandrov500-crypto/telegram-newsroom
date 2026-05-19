from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.doctrine.constitution import build_operational_constitution
from bot.editorial.flow_health.doctrine.continuity import analyze_complexity_continuity
from bot.editorial.flow_health.doctrine.digest import build_doctrine_digest_lines
from bot.editorial.flow_health.doctrine.doctrine_drift import detect_doctrine_drift
from bot.editorial.flow_health.doctrine.stewardship import (
    compute_stewardship_constitution,
    evaluate_institutional_stewardship_mode,
)


def doctrine_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational doctrine & stewardship constitution — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    cert = certification or gov.get("certification") or {}
    frz = freeze_registry or gov.get("freeze_registry") or {}
    omem = operational_memory or gov.get("operational_memory") or {}
    slim = slimming or gov.get("slimming") or {}
    rel = reliability or gov.get("reliability") or {}
    cockpit = cockpit or gov.get("cockpit") or {}

    constitution = build_operational_constitution(
        governance=gov,
        certification=cert,
        freeze_registry=frz,
        operational_memory=omem,
        slimming=slim,
        reliability=rel,
        cockpit=cockpit,
        ctx=ctx,
    )
    doctrine_drift = detect_doctrine_drift(
        constitution=constitution,
        freeze_registry=frz,
        certification=cert,
        operational_memory=omem,
        slimming=slim,
        cockpit=cockpit,
    )
    complexity = analyze_complexity_continuity(
        slimming=slim,
        freeze_registry=frz,
        certification=cert,
        cockpit=cockpit,
    )
    stewardship_constitution = compute_stewardship_constitution(
        constitution=constitution,
        doctrine_drift=doctrine_drift,
        complexity=complexity,
        certification=cert,
        freeze_registry=frz,
        operational_memory=omem,
    )
    institutional_mode = evaluate_institutional_stewardship_mode(
        certification=cert,
        freeze_registry=frz,
        operational_memory=omem,
        constitution=constitution,
        stewardship_constitution=stewardship_constitution,
        complexity=complexity,
        doctrine_drift=doctrine_drift,
    )
    ultra = bool(frz.get("ultra_quiet_digest"))
    doctrine_lines = build_doctrine_digest_lines(
        constitution=constitution,
        doctrine_drift=doctrine_drift,
        complexity=complexity,
        stewardship_constitution=stewardship_constitution,
        institutional_mode=institutional_mode,
        ultra_quiet=ultra,
    )

    return {
        "operational_constitution": constitution,
        "doctrine_drift": doctrine_drift,
        "complexity_continuity": complexity,
        "stewardship_constitution": stewardship_constitution,
        "institutional_stewardship_mode": institutional_mode,
        "doctrine_alignment_status": constitution.get("doctrine_alignment_status"),
        "stewardship_constitution_score": stewardship_constitution.get("stewardship_constitution_score"),
        "stewardship_constitution_band": stewardship_constitution.get("stewardship_constitution_band"),
        "doctrine_drift_detected": doctrine_drift.get("doctrine_drift_detected"),
        "doctrine_digest_lines": doctrine_lines,
    }


__all__ = ["doctrine_snapshot"]
