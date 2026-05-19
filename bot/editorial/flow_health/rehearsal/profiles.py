from __future__ import annotations

from typing import Any

_PROFILES: dict[str, dict[str, Any]] = {
    "normal_news_cycle": {
        "expected_behavior_summary": (
            "Steady cadence within targets; bounded modulation; trust guards unchanged."
        ),
        "modulation": "standard",
        "pruning": "normal",
    },
    "low_signal_weekend": {
        "expected_behavior_summary": (
            "Cadence softens; floor may activate; recovery digests rare; pruning strengthened."
        ),
        "modulation": "reduced",
        "pruning": "strong",
    },
    "breaking_news_spike": {
        "expected_behavior_summary": (
            "Surge/responsiveness lift; rhythm dampen relaxed; diversity guards hold; cadence may accelerate."
        ),
        "modulation": "responsive",
        "pruning": "normal",
    },
    "ingestion_partial_failure": {
        "expected_behavior_summary": (
            "Starvation floor bounded; degradation SIMPLIFIED possible; no publish forcing."
        ),
        "modulation": "conservative",
        "pruning": "strong",
    },
    "telemetry_degraded": {
        "expected_behavior_summary": (
            "Advisory layers reduced; core publish path unchanged; fail-open defaults."
        ),
        "modulation": "minimal",
        "pruning": "maximum",
    },
    "operator_absent": {
        "expected_behavior_summary": (
            "Conservative modulation; digest simplified; cadence continuity preserved; trust guards unchanged."
        ),
        "modulation": "conservative",
        "pruning": "strong",
    },
}


def infer_active_rehearsal_profile(ctx: dict[str, Any]) -> dict[str, Any]:
    """Map current runtime signals to nearest reference envelope — not a simulator."""
    gov = ctx.get("flow_governance") or {}
    flow = ctx.get("publish_funnel") or {}
    surge = gov.get("surge") or {}
    deg = gov.get("degradation") or {}
    absence = gov.get("operator_absence") or gov.get("reliability", {}).get("operator_absence") or {}

    profile = "normal_news_cycle"
    if str(deg.get("mode")) == "TELEMETRY_DEGRADED":
        profile = "telemetry_degraded"
    elif absence.get("operator_absence_level") in ("MILD_ABSENCE", "EXTENDED_ABSENCE"):
        profile = "operator_absent"
    elif (flow.get("starvation") or {}).get("detected"):
        profile = "ingestion_partial_failure"
    elif surge.get("surge_active"):
        profile = "breaking_news_spike"
    elif int((ctx.get("flow_cadence") or {}).get("actual_6h") or 0) < 2:
        profile = "low_signal_weekend"

    ref = _PROFILES.get(profile, _PROFILES["normal_news_cycle"])
    return {
        "active_profile": profile,
        "expected_behavior_summary": ref["expected_behavior_summary"],
        "reference_profiles": list(_PROFILES.keys()),
    }
