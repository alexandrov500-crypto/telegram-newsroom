from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def _parse_iso(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def run_adaptive_hygiene() -> dict[str, Any]:
    """
    Lazy prune stale adaptive state — no background loop.
    Called during governance snapshot collection.
    """
    if os.getenv("ADAPTIVE_HYGIENE_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"hygiene_ran": False}

    try:
        expire_hours = float(os.getenv("WARNING_EXPIRE_HOURS", "36"))
    except ValueError:
        expire_hours = 36.0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=expire_hours)

    st = load_state()
    pruned = 0
    hist = dict(st.get("warning_history") or {})
    for wid, entry in list(hist.items()):
        last = _parse_iso(str(entry.get("last_seen", "")))
        if last and last < cutoff and str(entry.get("tier", "")) != "CRITICAL":
            hist.pop(wid, None)
            pruned += 1

    daily = dict(st.get("baseline_daily") or {})
    max_days = int(os.getenv("BASELINE_RETAIN_DAYS", "14"))
    keys = sorted(daily.keys())[-max_days:]
    daily = {k: daily[k] for k in keys}

    relax_hist = [float(x) for x in (st.get("relaxation_budget_history") or [])][-48:]
    thresh_hist = [float(x) for x in (st.get("cluster_threshold_history") or [])][-48:]

    freshness = compute_adaptive_freshness(st)
    save_state(
        metrics={
            "warning_history": hist,
            "baseline_daily": daily,
            "relaxation_budget_history": relax_hist,
            "cluster_threshold_history": thresh_hist,
            "adaptive_freshness": freshness,
            "last_hygiene_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    minimize_meta: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.slimming.state_weight import minimize_adaptive_state

        minimize_meta = minimize_adaptive_state()
    except Exception:
        pass
    return {
        "hygiene_ran": True,
        "warnings_pruned": pruned,
        "adaptive_freshness": freshness,
        "state_minimize": minimize_meta,
    }


def compute_adaptive_freshness(st: dict[str, Any] | None = None) -> dict[str, Any]:
    st = st or load_state()
    scores: list[float] = []
    now = datetime.now(timezone.utc)

    last_h = _parse_iso(str(st.get("last_hygiene_at", "")))
    if last_h:
        age_h = (now - last_h).total_seconds() / 3600.0
        scores.append(max(0.0, 1.0 - age_h / 48.0))

    daily = st.get("baseline_daily") or {}
    if daily:
        last_day = sorted(daily.keys())[-1]
        try:
            day_dt = datetime.strptime(last_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_d = (now - day_dt).total_seconds() / 86400.0
            scores.append(max(0.0, 1.0 - age_d / 3.0))
        except ValueError:
            scores.append(0.5)
    else:
        scores.append(0.4)

    digest_seen = _parse_iso(str(st.get("last_operator_digest_at", "")))
    if digest_seen:
        age_d = (now - digest_seen).total_seconds() / 86400.0
        scores.append(max(0.0, 1.0 - age_d / 7.0))

    score = round(sum(scores) / max(1, len(scores)), 3) if scores else 0.5
    stale = score < 0.45
    return {"adaptive_freshness_score": score, "state_stale": stale}
