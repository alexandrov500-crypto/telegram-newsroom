from __future__ import annotations

import os
from typing import Any


def _pruning_enabled() -> bool:
    return os.getenv("TELEMETRY_PRUNING_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_actionable_context(ctx: dict[str, Any]) -> bool:
    """When true, show full cockpit detail."""
    flow = ctx.get("publish_funnel") or {}
    starve = (flow.get("starvation") or {}).get("detected")
    if starve:
        return True
    gov = ctx.get("flow_governance") or {}
    deg = gov.get("degradation") or {}
    if str(deg.get("mode", "NORMAL")) != "NORMAL":
        return True
    vit = (gov.get("vitality") or {}).get("stagnation") or {}
    if vit.get("stagnation_risk") in ("MODERATE", "HIGH"):
        return True
    if gov.get("baseline", {}).get("drift_detected"):
        return True
    trust = gov.get("trust_index") or {}
    if trust.get("metric_illusion_risk"):
        return True
    real = (gov.get("vitality") or {}).get("realism") or {}
    if not real.get("living_newsroom", True):
        return True
    cockpit = (gov.get("durability") or {}).get("cockpit") or {}
    if len(cockpit.get("active_warnings") or []) > 0:
        return True
    return False


# Substrings of low-value bullets when system is stable.
_LOW_IMPACT_PATTERNS = (
    "Configuration pressure low",
    "Digest dependency resolved",
    "Editorial freshness healthy",
    "Stable for 72h",
    "No material weekly",
    "accumulating weekly baseline",
)


def prune_cockpit_bullets(bullets: list[str], ctx: dict[str, Any]) -> dict[str, Any]:
    if not _pruning_enabled():
        return {"bullets": bullets, "pruned_count": 0, "pruning_active": False}

    if is_actionable_context(ctx):
        return {"bullets": bullets, "pruned_count": 0, "pruning_active": True}

    kept: list[str] = []
    pruned = 0
    for b in bullets:
        if any(p in b for p in _LOW_IMPACT_PATTERNS):
            pruned += 1
            continue
        kept.append(b)

    return {
        "bullets": kept[:5],
        "pruned_count": pruned,
        "pruning_active": True,
        "single_screen_target": len(kept) <= 5,
    }


def should_show_slimming_panel(ctx: dict[str, Any], slimming: dict[str, Any]) -> bool:
    """Only surface maintainability metrics when complexity is elevated."""
    if is_actionable_context(ctx):
        return False
    cfg = slimming.get("config_surface") or {}
    if cfg.get("config_complexity_band") in ("moderate", "high"):
        return True
    if int(slimming.get("consolidation", {}).get("heuristic_density") or 0) >= 5:
        return True
    weight = slimming.get("state_weight") or {}
    if float(weight.get("adaptive_state_weight") or 0) >= 0.55:
        return True
    return False
