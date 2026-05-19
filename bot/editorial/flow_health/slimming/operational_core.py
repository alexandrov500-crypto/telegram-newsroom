from __future__ import annotations

from typing import Any


def operational_core_map() -> dict[str, Any]:
    """Critical path vs advisory layers — maintenance orientation only."""
    return {
        "core": [
            {"id": "ingestion", "role": "source intake"},
            {"id": "clustering", "role": "story grouping"},
            {"id": "summarization", "role": "editorial text"},
            {"id": "publish_guard", "role": "trust + canary + content safety"},
            {"id": "publish_flow", "role": "telegram delivery"},
            {"id": "cadence_floor", "role": "starvation recovery (bounded)"},
        ],
        "advisory": [
            {"id": "vitality_governance", "role": "editorial aliveness telemetry"},
            {"id": "realism_index", "role": "living newsroom signal"},
            {"id": "baseline_governance", "role": "long-window drift"},
            {"id": "durability_modes", "role": "graceful degradation"},
            {"id": "signal_compression", "role": "digest cockpit"},
            {"id": "slimming_analysis", "role": "maintainability advisory"},
        ],
        "core_health_indicators": [
            "publish_success_rate",
            "starvation_detected",
            "degradation_mode",
            "canary_hourly_cap",
        ],
    }


def assess_core_health(ctx: dict[str, Any]) -> dict[str, Any]:
    flow = ctx.get("publish_funnel") or {}
    starve = bool((flow.get("starvation") or {}).get("detected"))
    rate = ctx.get("publish_success_rate")
    deg = (ctx.get("flow_governance") or {}).get("degradation") or {}
    mode = str(deg.get("mode", "NORMAL"))
    healthy = not starve and mode == "NORMAL" and (rate is None or float(rate) >= 0.5)
    return {
        "operational_core_healthy": healthy,
        "starvation": starve,
        "degradation_mode": mode,
        "publish_success_rate": rate,
    }
