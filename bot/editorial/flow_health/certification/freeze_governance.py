from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.reliability.freeze_discipline import analyze_freeze_discipline
from bot.editorial.flow_health.state import load_state

_FROZEN_CORE = frozenset(
    {
        "publish_guard",
        "publish_flow",
        "clustering",
        "ingestion",
        "hallucination_guards",
        "misinformation_blockers",
        "trust_gates",
    },
)
_RESTRICTED_TUNING = frozenset(
    {
        "cadence_targets",
        "flow_health_floor",
        "relaxation_budget",
        "canary_cap",
        "cluster_threshold",
    },
)
_EXPERIMENTAL = frozenset(
    {
        "digest_wording",
        "vitality_telemetry",
        "trust_calibration",
        "ops_evidence",
    },
)


def assess_stabilization_freeze(
    *,
    config_pressure: dict[str, Any] | None = None,
    freeze_discipline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Distinguish frozen core, restricted tuning, experimental — advisory only."""
    discipline = freeze_discipline or analyze_freeze_discipline(config_pressure=config_pressure)
    cfg = config_pressure or {}
    advanced = int(cfg.get("advanced_touched") or discipline.get("config_volatility_signals") or 0)
    st = load_state()
    violations: list[str] = []

    if discipline.get("freeze_discipline_status") == "HIGH_TUNING_CHURN":
        violations.append("high_config_churn")
    if advanced >= 5:
        violations.append("advanced_surface_over_touched")
    hist = list(st.get("degradation_mode_history") or [])[-8:]
    if len(hist) >= 6:
        flips = sum(
            1
            for i in range(1, len(hist))
            if str(hist[i].get("mode")) != str(hist[i - 1].get("mode"))
        )
        if flips >= 4:
            violations.append("subsystem_instability_modes")

    status = "STABLE_FREEZE"
    if violations:
        status = "FREEZE_AT_RISK" if len(violations) == 1 else "FREEZE_VIOLATIONS"

    return {
        "stabilization_freeze_status": status,
        "freeze_violations": violations,
        "frozen_operational_core": sorted(_FROZEN_CORE),
        "restricted_tuning_areas": sorted(_RESTRICTED_TUNING),
        "experimental_zones": sorted(_EXPERIMENTAL),
        "freeze_discipline": discipline,
        "tuning_frequency_signal": advanced,
    }
