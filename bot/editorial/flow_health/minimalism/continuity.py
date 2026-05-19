from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def touch_quiet_infrastructure(
    *,
    quiet_today: bool,
) -> dict[str, Any]:
    """Days without governance inflation — bounded persistence."""
    try:
        st = load_state()
        cont = dict(st.get("minimalism_continuity") or {})
        days: dict[str, bool] = dict(cont.get("quiet_days") or {})
        days[_utc_day()] = quiet_today
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
            band = "INFRASTRUCTURAL"
        elif streak >= 14:
            band = "QUIET"
        elif streak >= 7:
            band = "STABILIZING"
        cont["quiet_days"] = days
        cont["quiet_infrastructure_streak_days"] = streak
        cont["quiet_infrastructure_band"] = band
        save_state(metrics={"minimalism_continuity": cont})
        return cont
    except Exception:
        return {"quiet_infrastructure_streak_days": 0, "quiet_infrastructure_band": "ACTIVE_EVOLUTION"}


def is_quiet_infrastructure_day(
    *,
    governance: dict[str, Any] | None = None,
    entropy: dict[str, Any] | None = None,
) -> bool:
    gov = governance or {}
    ent = entropy or {}
    frz = gov.get("freeze_registry") or {}
    cert = gov.get("certification") or {}
    return bool(
        frz.get("ultra_quiet_digest")
        and (cert.get("change_pressure") or {}).get("change_pressure_band") == "LOW"
        and not ent.get("entropy_elevated")
        and str((gov.get("degradation") or {}).get("mode", "NORMAL")) == "NORMAL"
    )
