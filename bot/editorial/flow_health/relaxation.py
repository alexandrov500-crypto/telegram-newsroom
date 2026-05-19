from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.funnel import funnel_summary
from bot.editorial.flow_health.state import clear_recovery_activation, load_state, touch_recovery_activation


def _budget_max() -> float:
    try:
        return float(os.getenv("RELAXATION_BUDGET_MAX", "0.25"))
    except ValueError:
        return 0.25


def _hysteresis_minutes() -> float:
    try:
        return float(os.getenv("RECOVERY_HYSTERESIS_MINUTES", "90"))
    except ValueError:
        return 90.0


def hysteresis_multiplier(*, starving: bool) -> float:
    """
    1.0 while starving; after starvation ends, linear decay to 0 over hysteresis window.
  Lazy — no background timers.
    """
    if starving:
        touch_recovery_activation()
        return 1.0

    st = load_state()
    raw = st.get("recovery_activated_at")
    if not raw:
        return 0.0

    try:
        started = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except ValueError:
        clear_recovery_activation()
        return 0.0

    elapsed_min = (datetime.now(timezone.utc) - started).total_seconds() / 60.0
    window = _hysteresis_minutes()
    if elapsed_min >= window:
        clear_recovery_activation()
        return 0.0
    return max(0.0, 1.0 - elapsed_min / window)


def compute_relaxation_components(
    *,
    starving: bool,
    low_volume: bool,
    overnight: bool,
    burst: bool,
) -> dict[str, float]:
    """Per-modifier weights (heuristic units, not additive probabilities)."""
    c: dict[str, float] = {}
    if starving:
        c["starvation"] = 0.12
    if low_volume:
        c["low_volume"] = 0.06
    if overnight:
        c["overnight"] = 0.05
    if burst:
        c["burst_tighten"] = -0.04
    if starving:
        c["quality_softening"] = 0.08
        c["fatigue_relax"] = 0.07
        c["cluster_relax"] = 0.10
    return c


def apply_relaxation_budget(components: dict[str, float]) -> dict[str, Any]:
    positive = sum(v for v in components.values() if v > 0)
    negative = sum(v for v in components.values() if v < 0)
    raw_combined = max(0.0, positive + negative)
    budget_max = _budget_max()
    scale = 1.0
    if raw_combined > budget_max > 0:
        scale = budget_max / raw_combined
    budget_used = min(raw_combined, budget_max)

    return {
        "components": components,
        "raw_combined": round(raw_combined, 4),
        "relaxation_budget_used": round(budget_used, 4),
        "relaxation_budget_max": budget_max,
        "budget_scale": round(scale, 4),
    }


def effective_relaxation_scale(
    *,
    starving: bool,
    low_volume: bool,
    overnight: bool,
    burst: bool,
) -> dict[str, Any]:
    hysteresis = hysteresis_multiplier(starving=starving)
    components = compute_relaxation_components(
        starving=starving,
        low_volume=low_volume,
        overnight=overnight,
        burst=burst,
    )
    rhythm_mult = 1.0
    rhythm_band = "steady"
    try:
        from bot.editorial.flow_health.rhythm import compute_rhythm_modulation

        rhythm = compute_rhythm_modulation()
        rhythm_mult = float(rhythm.get("rhythm_multiplier") or 1.0)
        rhythm_band = str(rhythm.get("rhythm_band") or "steady")
        components = {
            k: (v * rhythm_mult if v > 0 else v) for k, v in components.items()
        }
    except Exception:
        pass
    budget = apply_relaxation_budget(components)
    effective_scale = budget["budget_scale"] * hysteresis
    try:
        from bot.editorial.flow_health.degradation import apply_degradation_scale, gates_for_current_mode

        gates = gates_for_current_mode()
        if not gates.get("advanced_calibration", True):
            effective_scale = min(effective_scale, 0.5)
        st = load_state()
        effective_scale = apply_degradation_scale(
            effective_scale,
            {"modulation_scale": float(st.get("last_modulation_scale") or 1.0)},
        )
    except Exception:
        pass
    return {
        **budget,
        "hysteresis_multiplier": round(hysteresis, 4),
        "effective_scale": round(effective_scale, 4),
        "rhythm_multiplier": round(rhythm_mult, 4),
        "rhythm_band": rhythm_band,
    }
