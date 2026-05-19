from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def touch_complexity_continuity(*, bounded: bool) -> int:
    """Rolling days of constitutionally bounded complexity surface."""
    try:
        st = load_state()
        cont = dict(st.get("doctrine_continuity") or {})
        days: dict[str, bool] = dict(cont.get("bounded_days") or {})
        days[_utc_day()] = bounded
        keys = sorted(days.keys())[-35:]
        days = {k: days[k] for k in keys}
        streak = 0
        for k in reversed(keys):
            if days.get(k):
                streak += 1
            else:
                break
        cont["bounded_days"] = days
        cont["bounded_streak_days"] = streak
        save_state(metrics={"doctrine_continuity": cont})
        return streak
    except Exception:
        return 0


def analyze_complexity_continuity(
    *,
    slimming: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lightweight complexity continuity — bounded heuristics only."""
    slim = slimming or {}
    frz = freeze_registry or {}
    cert = certification or {}
    cockpit = cockpit or {}

    cfg = (slim.get("config_surface") or {}).get("config_complexity_band", "low")
    heuristic_n = int((slim.get("consolidation") or {}).get("heuristic_density") or 0)
    experimental = float(frz.get("experimental_surface_ratio") or 0)
    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    warn_n = len(cockpit.get("active_warnings") or [])

    bounded = cfg == "low" and heuristic_n < 6 and experimental < 0.3 and chg == "LOW"
    streak = touch_complexity_continuity(bounded=bounded)

    advisories: list[str] = []
    if bounded and streak >= 7:
        advisories.append("Operational surface remains constitutionally bounded")
    if streak >= 14:
        advisories.append(f"Complexity surface stable for {streak}d")
    if heuristic_n >= 5:
        advisories.append("Governance layering approaching doctrine drift")
    if experimental >= 0.28:
        advisories.append("Experimental surface exceeds calmness doctrine containment")
    if warn_n >= 6:
        advisories.append("Telemetry expansion exceeds calmness doctrine")

    return {
        "complexity_bounded": bounded,
        "bounded_streak_days": streak,
        "complexity_advisories": advisories[:4],
    }
