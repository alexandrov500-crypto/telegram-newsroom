from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def touch_canonical_truth_continuity(*, coherent_today: bool) -> dict[str, Any]:
    """Days of consistent governance propagation — bounded persistence."""
    try:
        st = load_state()
        cont = dict(st.get("observability_continuity") or {})
        days: dict[str, bool] = dict(cont.get("canonical_days") or {})
        days[_utc_day()] = coherent_today
        keys = sorted(days.keys())[-40:]
        days = {k: days[k] for k in keys}
        streak = 0
        for k in reversed(keys):
            if days.get(k):
                streak += 1
            else:
                break
        band = "TRANSITIONAL"
        if streak >= 28:
            band = "CANONICAL"
        elif streak >= 14:
            band = "COHERENT"
        elif streak >= 7:
            band = "STABLE"
        cont["canonical_days"] = days
        cont["canonical_truth_streak_days"] = streak
        cont["canonical_truth_band"] = band
        save_state(metrics={"observability_continuity": cont})
        return cont
    except Exception:
        return {"canonical_truth_streak_days": 0, "canonical_truth_band": "TRANSITIONAL"}


def is_canonical_truth_day(
    *,
    cohesion: dict[str, Any] | None = None,
    integrity: dict[str, Any] | None = None,
    propagation: dict[str, Any] | None = None,
    drift: dict[str, Any] | None = None,
) -> bool:
    return bool(
        cohesion.get("governance_cohesion_status") in ("COHERENT", "CANONICAL")
        and integrity.get("observability_integrity_band") in ("STABLE", "CANONICAL")
        and propagation.get("propagation_coherent")
        and not drift.get("observability_drift_detected")
    )
