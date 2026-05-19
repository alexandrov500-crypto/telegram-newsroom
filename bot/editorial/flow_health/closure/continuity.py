from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def touch_steady_state_continuity(*, steady_today: bool) -> dict[str, Any]:
    """Maturity without expansion pressure — bounded persistence."""
    try:
        st = load_state()
        cont = dict(st.get("closure_continuity") or {})
        days: dict[str, bool] = dict(cont.get("steady_days") or {})
        days[_utc_day()] = steady_today
        keys = sorted(days.keys())[-45:]
        days = {k: days[k] for k in keys}
        streak = 0
        for k in reversed(keys):
            if days.get(k):
                streak += 1
            else:
                break
        band = "ACTIVE_FORMATION"
        if streak >= 35:
            band = "OPERATIONALLY_COMPLETE"
        elif streak >= 21:
            band = "STEADY"
        elif streak >= 10:
            band = "STABILIZED"
        cont["steady_days"] = days
        cont["steady_state_streak_days"] = streak
        cont["steady_state_band"] = band
        save_state(metrics={"closure_continuity": cont})
        return cont
    except Exception:
        return {"steady_state_streak_days": 0, "steady_state_band": "ACTIVE_FORMATION"}


def is_steady_state_day(
    *,
    governance: dict[str, Any] | None = None,
    sufficiency: dict[str, Any] | None = None,
    expansion: dict[str, Any] | None = None,
) -> bool:
    gov = governance or {}
    suff = sufficiency or {}
    exp = expansion or {}
    frz = gov.get("freeze_registry") or {}
    rehe = gov.get("rehearsal") or {}
    return bool(
        suff.get("architectural_sufficiency")
        and not exp.get("expansion_pressure_detected")
        and frz.get("ultra_quiet_digest")
        and (rehe.get("drift_boundaries") or {}).get("drift_boundary_status") == "WITHIN_BOUNDS"
        and str((gov.get("degradation") or {}).get("mode", "NORMAL")) == "NORMAL"
    )
