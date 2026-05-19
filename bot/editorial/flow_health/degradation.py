from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state

MODES = ("NORMAL", "SIMPLIFIED", "SAFE_BASELINE", "TELEMETRY_DEGRADED")


def _modulation_scale(mode: str) -> float:
    return {
        "NORMAL": 1.0,
        "SIMPLIFIED": 0.65,
        "SAFE_BASELINE": 0.35,
        "TELEMETRY_DEGRADED": 0.5,
    }.get(mode, 0.65)


def detect_degradation_mode(
    *,
    baseline: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
    telemetry_ok: bool = True,
    vitality_stale: bool = False,
) -> dict[str, Any]:
    """
    Progressive degradation — disables secondary heuristics, not core publish path.
    Fail-open → NORMAL.
    """
    if os.getenv("DEGRADATION_MODES_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"mode": "NORMAL", "modulation_scale": 1.0, "reasons": []}

    reasons: list[str] = []
    mode = "NORMAL"

    st = load_state()
    if not telemetry_ok:
        mode = "TELEMETRY_DEGRADED"
        reasons.append("telemetry_partial_failure")

    if vitality_stale:
        reasons.append("vitality_baseline_stale")
        if mode == "NORMAL":
            mode = "SIMPLIFIED"

    if baseline:
        if baseline.get("drift_detected"):
            reasons.append("baseline_drift_excessive")
            mode = "SIMPLIFIED"
        dev = float(baseline.get("baseline_deviation") or 0)
        if dev >= float(os.getenv("DEGRADATION_DEVIATION_SAFE", "0.32")):
            mode = "SAFE_BASELINE"
            reasons.append("high_baseline_deviation")

    if adaptive:
        relax = adaptive.get("relaxation") or {}
        if float(relax.get("relaxation_budget_used") or 0) >= float(
            relax.get("relaxation_budget_max") or 0.25,
        ) * 0.95:
            reasons.append("relaxation_budget_saturated")
            if mode == "NORMAL":
                mode = "SIMPLIFIED"

    low_obs = st.get("low_observability_active")
    if low_obs:
        reasons.append("low_observability_survival")
        if mode in ("NORMAL", "SIMPLIFIED"):
            mode = "SIMPLIFIED"

    hist = st.get("degradation_mode_history") or []
    hist.append({"mode": mode, "at": datetime.now(timezone.utc).isoformat()})
    try:
        save_state(
            metrics={
                "degradation_mode_history": hist[-24:],
                "last_degradation_mode": mode,
                "last_modulation_scale": _modulation_scale(mode),
            },
        )
    except Exception:
        pass

    gates = heuristic_gates(mode)
    set_degradation_gates(gates)
    return {
        "mode": mode,
        "modulation_scale": _modulation_scale(mode),
        "reasons": reasons,
        "gates": gates,
    }


def heuristic_gates(mode: str) -> dict[str, bool]:
    return {
        "vitality_nudges": mode == "NORMAL",
        "responsiveness_boost": mode in ("NORMAL", "SIMPLIFIED"),
        "surge_boost": mode != "SAFE_BASELINE",
        "rhythm_dampen": mode == "NORMAL",
        "longtail_nudges": mode not in ("SAFE_BASELINE", "TELEMETRY_DEGRADED"),
        "category_recovery_nudges": mode != "TELEMETRY_DEGRADED",
        "advanced_calibration": mode == "NORMAL",
    }


def apply_degradation_scale(effective_scale: float, degradation: dict[str, Any] | None) -> float:
    if not degradation:
        return effective_scale
    return round(effective_scale * float(degradation.get("modulation_scale") or 1.0), 4)


_cached_gates: dict[str, bool] | None = None


def set_degradation_gates(gates: dict[str, bool]) -> None:
    global _cached_gates
    _cached_gates = gates


def gates_for_current_mode() -> dict[str, bool]:
    if _cached_gates is not None:
        return _cached_gates
    try:
        st = load_state()
        mode = str(st.get("last_degradation_mode") or "NORMAL")
        return heuristic_gates(mode)
    except Exception:
        return heuristic_gates("NORMAL")
