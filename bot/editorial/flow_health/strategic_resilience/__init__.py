from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.strategic_resilience.continuity import touch_sustainability_memory
from bot.editorial.flow_health.strategic_resilience.digest import build_resilience_digest_lines
from bot.editorial.flow_health.strategic_resilience.erosion import detect_architectural_erosion
from bot.editorial.flow_health.strategic_resilience.resilience import compute_strategic_resilience_index
from bot.editorial.flow_health.strategic_resilience.stewardship import (
    assess_stewardship_fatigue,
    estimate_sustainability_horizon,
    evaluate_long_horizon_sustainability,
)
from bot.editorial.flow_health.strategic_resilience.sustainability import assess_sustainability_dimensions


def strategic_resilience_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    editorial_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Strategic resilience & long-horizon sustainability — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    cert = certification or gov.get("certification") or {}
    frz = freeze_registry or gov.get("freeze_registry") or {}
    omem = operational_memory or gov.get("operational_memory") or {}
    doc = doctrine or gov.get("doctrine") or {}
    rel = reliability or gov.get("reliability") or {}
    cockpit = cockpit or gov.get("cockpit") or {}

    sustainability = assess_sustainability_dimensions(
        governance=gov,
        certification=cert,
        freeze_registry=frz,
        operational_memory=omem,
        doctrine=doc,
        reliability=rel,
        ctx=ctx,
        editorial_identity=editorial_identity,
    )
    erosion = detect_architectural_erosion(
        governance=gov,
        certification=cert,
        freeze_registry=frz,
        operational_memory=omem,
        doctrine=doc,
        reliability=rel,
        cockpit=cockpit,
        sustainability=sustainability,
    )
    resilience = compute_strategic_resilience_index(
        sustainability=sustainability,
        erosion=erosion,
        operational_memory=omem,
        doctrine=doc,
        freeze_registry=frz,
        reliability=rel,
        certification=cert,
    )
    fatigue = assess_stewardship_fatigue(
        certification=cert,
        operational_memory=omem,
        freeze_registry=frz,
        erosion=erosion,
    )
    horizon = estimate_sustainability_horizon(
        resilience=resilience,
        erosion=erosion,
        doctrine=doc,
        operational_memory=omem,
        freeze_registry=frz,
        sustainability=sustainability,
        fatigue=fatigue,
    )
    memory = touch_sustainability_memory(
        erosion=erosion,
        resilience=resilience,
        doctrine=doc,
        operational_memory=omem,
    )
    long_horizon = evaluate_long_horizon_sustainability(
        resilience=resilience,
        horizon=horizon,
        erosion=erosion,
        fatigue=fatigue,
        doctrine=doc,
    )
    ultra = bool(frz.get("ultra_quiet_digest"))
    digest_lines = build_resilience_digest_lines(
        resilience=resilience,
        horizon=horizon,
        erosion=erosion,
        fatigue=fatigue,
        long_horizon=long_horizon,
        ultra_quiet=ultra,
    )

    return {
        "sustainability": sustainability,
        "erosion": erosion,
        "strategic_resilience": resilience,
        "stewardship_fatigue": fatigue,
        "sustainability_horizon": horizon,
        "strategic_resilience_memory": memory,
        "long_horizon_sustainability": long_horizon,
        "strategic_resilience_index": resilience.get("strategic_resilience_index"),
        "strategic_resilience_band": resilience.get("strategic_resilience_band"),
        "sustainability_horizon_days": horizon.get("sustainability_horizon_days"),
        "sustainability_horizon_band": horizon.get("sustainability_horizon_band"),
        "architectural_erosion_detected": erosion.get("architectural_erosion_detected"),
        "stewardship_fatigue_detected": fatigue.get("stewardship_fatigue_detected"),
        "resilience_digest_lines": digest_lines,
    }


__all__ = ["strategic_resilience_snapshot"]
