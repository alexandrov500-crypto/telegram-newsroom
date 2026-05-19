from __future__ import annotations

import os
from typing import Any

from bot.editorial.flow_health.state import load_state

_FROZEN = frozenset(
    {
        "publish_guard",
        "publish_flow",
        "clustering",
        "ingestion",
        "canary_mode",
        "hallucination_guards",
    },
)
_TUNABLE = frozenset(
    {
        "flow_health_floor",
        "relaxation_budget",
        "cadence_targets",
        "canary_cap",
        "digest_discipline",
    },
)
_EXPERIMENTAL = frozenset(
    {
        "vitality_telemetry",
        "realism_index",
        "slimming_analysis",
        "trust_calibration",
        "ops_evidence",
    },
)


def analyze_freeze_discipline(*, config_pressure: dict[str, Any] | None = None) -> dict[str, Any]:
    """Advisory maintenance-mode classification — no enforcement."""
    cfg = config_pressure or {}
    advanced = int(cfg.get("advanced_touched") or 0)
    st = load_state()
    audits = st.get("weekly_audits") or {}
    mode_changes = 0
    keys = sorted(audits.keys())[-4:]
    for k in keys:
        if str((audits.get(k) or {}).get("degradation_mode", "NORMAL")) != "NORMAL":
            mode_changes += 1

    churn_risk = advanced >= 4 or mode_changes >= 3
    status = "MAINTENANCE_STABLE"
    if churn_risk:
        status = "HIGH_TUNING_CHURN"
    elif advanced >= 2:
        status = "ACTIVE_TUNING"

    return {
        "freeze_discipline_status": status,
        "frozen_subsystems": sorted(_FROZEN)[:8],
        "tunable_subsystems": sorted(_TUNABLE)[:8],
        "experimental_subsystems": sorted(_EXPERIMENTAL)[:6],
        "config_volatility_signals": advanced,
        "recent_degradation_weeks": mode_changes,
        "recommendation": "freeze_core_tune_advisory_only" if churn_risk else "operational_maintenance_mode",
    }
