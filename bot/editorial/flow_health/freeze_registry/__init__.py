from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.freeze_registry.digest import (
    build_freeze_stewardship_lines,
    should_ultra_quiet_digest,
)
from bot.editorial.flow_health.freeze_registry.drift import touch_evolution_ledger
from bot.editorial.flow_health.freeze_registry.exposure import (
    compute_drift_exposure_index,
    estimate_stewardship_horizon,
)
from bot.editorial.flow_health.freeze_registry.registry import build_freeze_registry


def freeze_registry_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational freeze registry + evolution ledger — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    cert = certification or gov.get("certification") or {}
    rehe = rehearsal or gov.get("rehearsal") or {}
    rel = reliability or gov.get("reliability") or {}
    cockpit = cockpit or {}

    registry = build_freeze_registry()
    evolution_ledger = touch_evolution_ledger(governance=gov, certification=cert, ctx=ctx)
    drift_exposure = compute_drift_exposure_index(
        registry=registry,
        certification=cert,
        rehearsal=rehe,
        governance=gov,
        cockpit=cockpit,
        evolution_ledger=evolution_ledger,
    )
    horizon = estimate_stewardship_horizon(
        certification=cert,
        rehearsal=rehe,
        reliability=rel,
        drift_exposure=drift_exposure,
        cockpit=cockpit,
    )

    all_calm = (
        str((gov.get("degradation") or {}).get("mode", "NORMAL")) == "NORMAL"
        and (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY"
    )
    ultra = should_ultra_quiet_digest(
        certification=cert,
        drift_exposure=drift_exposure,
        horizon=horizon,
        all_calm=all_calm,
    )
    stewardship_lines = build_freeze_stewardship_lines(
        freeze_registry=registry,
        drift_exposure=drift_exposure,
        horizon=horizon,
        certification=cert,
        evolution_ledger=evolution_ledger,
        ultra_quiet=ultra,
    )

    return {
        "freeze_registry": registry,
        "evolution_ledger": evolution_ledger,
        "drift_exposure": drift_exposure,
        "stewardship_horizon": horizon,
        "ultra_quiet_digest": ultra,
        "stewardship_summary_lines": stewardship_lines,
    }


__all__ = ["freeze_registry_snapshot"]
