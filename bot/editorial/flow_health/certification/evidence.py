from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _streak_true(days: dict[str, dict[str, Any]], key: str) -> int:
    """Consecutive calendar days (from latest) where key is truthy."""
    keys = sorted(days.keys())
    n = 0
    for day in reversed(keys):
        if days[day].get(key):
            n += 1
        else:
            break
    return n


def touch_evidence_daily(
    *,
    ctx: dict[str, Any] | None = None,
    degradation_mode: str = "NORMAL",
    warning_pressure: float = 0.0,
    calm_recovery: bool = True,
) -> None:
    """Rolling 21-day evidence flags — compact, no audit framework."""
    ctx = ctx or {}
    flow = ctx.get("publish_funnel") or {}
    try:
        st = load_state()
        daily: dict[str, dict[str, Any]] = dict(st.get("evidence_daily") or {})
        daily[_utc_day()] = {
            "no_starvation": not bool((flow.get("starvation") or {}).get("detected")),
            "deg_normal": str(degradation_mode) == "NORMAL",
            "low_warnings": warning_pressure < 0.28,
            "calm_recovery": calm_recovery,
            "stable_cadence": float((ctx.get("flow_cadence") or {}).get("cadence_health") or 0) >= 0.45,
        }
        keys = sorted(daily.keys())[-21:]
        save_state(metrics={"evidence_daily": {k: daily[k] for k in keys}})
    except Exception:
        pass


def build_operational_evidence_summary(
    *,
    ctx: dict[str, Any] | None = None,
    warning_pressure: float = 0.0,
    degradation_mode: str = "NORMAL",
    calm_recovery: bool = True,
) -> dict[str, Any]:
    """Rolling evidence narratives — derived + light daily touch."""
    touch_evidence_daily(
        ctx=ctx,
        degradation_mode=degradation_mode,
        warning_pressure=warning_pressure,
        calm_recovery=calm_recovery,
    )
    st = load_state()
    daily = dict(st.get("evidence_daily") or {})
    bullets: list[str] = []

    starve_days = _streak_true(daily, "no_starvation")
    if starve_days >= 3:
        bullets.append(f"{starve_days} consecutive day(s) without starvation")

    calm_days = _streak_true(daily, "calm_recovery")
    if calm_days >= 3:
        bullets.append(f"{calm_days}-day calm recovery envelope")

    norm_days = _streak_true(daily, "deg_normal")
    if norm_days >= 5:
        bullets.append(f"{norm_days} day(s) bounded degradation (NORMAL)")

    warn_days = _streak_true(daily, "low_warnings")
    if warn_days >= 4:
        bullets.append(f"{warn_days} day(s) low warning pressure")

    cadence_days = _streak_true(daily, "stable_cadence")
    if cadence_days >= 5:
        bullets.append(f"{cadence_days} day(s) stable cadence window")

    base_daily = st.get("baseline_daily") or {}
    if len(base_daily) >= 7:
        bullets.append(f"{len(base_daily)} day(s) baseline rolls on file")

    audits = st.get("weekly_audits") or {}
    normal_weeks = sum(
        1 for k in sorted(audits.keys())[-4:] if str((audits[k] or {}).get("degradation_mode")) == "NORMAL"
    )
    if normal_weeks >= 3 and len(audits) >= 3:
        bullets.append(f"{normal_weeks} recent week(s) without degradation escalation")

    hist = list(st.get("degradation_mode_history") or [])
    if len(hist) >= 12 and all(str(h.get("mode", "NORMAL")) == "NORMAL" for h in hist[-12:]):
        bullets.append("Extended uninterrupted NORMAL degradation window")

    return {
        "operational_evidence_summary": bullets[:6],
        "evidence_streaks": {
            "no_starvation_days": starve_days,
            "calm_recovery_days": calm_days,
            "normal_degradation_days": norm_days,
            "low_warning_days": warn_days,
            "stable_cadence_days": cadence_days,
        },
    }
