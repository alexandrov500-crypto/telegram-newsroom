from __future__ import annotations

import os
from typing import Any

# Pilot-critical — do not recommend removal.
_CORE: frozenset[str] = frozenset(
    {
        "PUBLISH_FLOW_HEALTH_ENABLED",
        "PUBLISH_FLOOR_ENABLED",
        "LIVE_CANARY_MAX_PER_HOUR",
        "CANARY_CAP_CEILING",
        "PUBLISH_DIVERSITY_GATE_ENABLED",
        "RELAXATION_BUDGET_MAX",
        "MIN_PUBLISH_PER_6H",
        "CADENCE_TARGETS",
        "ARCHITECTURE_STABILITY_PHASE",
        "RUNTIME_PROFILE",
    },
)

_ADVANCED: frozenset[str] = frozenset(
    {
        "RHYTHM_SMOOTHING_FACTOR",
        "RHYTHM_BURST_2H",
        "SURGE_MIN_FETCHED_6H",
        "RESPONSIVENESS_RHYTHM_BOOST",
        "MIN_STORY_DISTANCE_FOR_FLOOR",
        "BASELINE_DEVIATION_WARN",
        "DIGEST_MAX_RATIO_24H",
        "STAGNATION_RISK_HIGH",
        "DEGRADATION_DEVIATION_SAFE",
    },
)

_EXPERIMENTAL: frozenset[str] = frozenset(
    {
        "CANARY_CADENCE_APPROVAL_RELAX",
        "WARNING_COLLAPSE_AFTER",
        "IMMUNITY_VITALITY_FLOOR",
    },
)

# Documented in .env.example with stable defaults — safe to freeze in pilot.
_FROZEN_DEFAULTS: dict[str, str] = {
    "DIGEST_SIGNAL_COMPRESSION": "true",
    "DEGRADATION_MODES_ENABLED": "true",
    "ADAPTIVE_HYGIENE_ENABLED": "true",
    "BASELINE_IMMUNITY_ENABLED": "true",
}


def analyze_config_surface() -> dict[str, Any]:
    """Classify tuning surface — advisory config_complexity_score."""
    known = _CORE | _ADVANCED | _EXPERIMENTAL | set(_FROZEN_DEFAULTS)
    set_in_env = {k for k in known if os.getenv(k) is not None}
    non_default = 0
    for key in set_in_env:
        if key in _FROZEN_DEFAULTS and os.getenv(key) == _FROZEN_DEFAULTS[key]:
            continue
        if key in _CORE:
            continue
        non_default += 1

    removable_candidates = [
        k for k in _EXPERIMENTAL if os.getenv(k) is None
    ]
    frozen_recommendations = list(_FROZEN_DEFAULTS.keys())

    complexity = round(
        min(1.0, (len(set_in_env) / max(1, len(known))) * 0.5 + non_default * 0.04),
        3,
    )
    band = "low"
    if complexity >= 0.55:
        band = "high"
    elif complexity >= 0.32:
        band = "moderate"

    return {
        "config_complexity_score": complexity,
        "config_complexity_band": band,
        "core_count": len(_CORE),
        "advanced_touched": non_default,
        "experimental_unset": len(removable_candidates),
        "frozen_recommendations": frozen_recommendations[:8],
        "grouped": {
            "core": sorted(_CORE)[:10],
            "advanced": sorted(_ADVANCED)[:10],
        },
    }
