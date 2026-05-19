from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def touch_convergence_continuity(*, converged_today: bool) -> dict[str, Any]:
    """Days of stable explanatory governance model — bounded persistence."""
    try:
        st = load_state()
        cont = dict(st.get("convergence_continuity") or {})
        days: dict[str, bool] = dict(cont.get("converged_days") or {})
        days[_utc_day()] = converged_today
        keys = sorted(days.keys())[-40:]
        days = {k: days[k] for k in keys}
        streak = 0
        for k in reversed(keys):
            if days.get(k):
                streak += 1
            else:
                break
        band = "ACTIVE_EVOLUTION"
        if streak >= 28:
            band = "FINALIZED_CONTINUITY"
        elif streak >= 14:
            band = "CONVERGED"
        elif streak >= 7:
            band = "STABILIZED"
        cont["converged_days"] = days
        cont["governance_convergence_streak_days"] = streak
        cont["governance_convergence_band"] = band
        save_state(metrics={"convergence_continuity": cont})
        return cont
    except Exception:
        return {
            "governance_convergence_streak_days": 0,
            "governance_convergence_band": "ACTIVE_EVOLUTION",
        }


def is_convergence_day(
    *,
    converged: dict[str, Any] | None = None,
    recursion: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
) -> bool:
    return bool(
        converged.get("governance_converged")
        and not recursion.get("stewardship_recursion_detected")
        and float(novelty.get("stewardship_novelty_decay") or 0) >= 0.55
    )
