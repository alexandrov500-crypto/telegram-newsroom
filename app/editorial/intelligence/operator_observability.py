"""Operator intelligence and newsroom observability snapshot."""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.editorial.intelligence.trend_memory import (
    cluster_snapshot,
    time_of_day_cluster_fit,
    trend_memory_events,
)


def _safe_mean(values: list[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _session_key(ts: float, *, tz_name: str = "Europe/Moscow") -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    h = datetime.fromtimestamp(ts, tz=UTC).astimezone(tz).hour
    if 8 <= h < 10:
        return "morning_briefing"
    if 10 <= h < 19:
        return "intraday_signals"
    if 19 <= h < 22:
        return "evening_recap"
    return "offhours"


def _cluster_rows(runtime_dir: str, *, now_ts: float) -> list[dict[str, Any]]:
    events = trend_memory_events(runtime_dir, hours=24 * 7, now_ts=now_ts)
    keys = sorted({str(e.get("cluster_key") or "") for e in events if str(e.get("cluster_key") or "").strip()})
    rows: list[dict[str, Any]] = []
    total_24 = max(
        1,
        len([e for e in events if float(e.get("ts") or 0.0) >= now_ts - 24 * 3600]),
    )
    for k in keys:
        s = cluster_snapshot(runtime_dir, cluster_key=k, now=now_ts)
        row = {
            "cluster_key": k,
            "momentum_score": s.momentum_score,
            "growth_velocity": s.growth_velocity,
            "saturation_level": s.saturation_level,
            "fatigue_probability": s.fatigue_probability,
            "repost_velocity": s.forward_velocity,
            "retention_strength": s.open_retention,
            "open_loop_strength": s.narrative_momentum,
            "hashtag_efficiency": round(_clamp(s.quoteability * 0.45 + s.repost_rate * 0.35 + s.screenshot_probability * 0.2), 4),
            "cadence_fit": round(time_of_day_cluster_fit(runtime_dir, cluster_key=k), 4),
            "signal_density": round(s.events_24h / total_24, 4),
            "events_24h": s.events_24h,
            "events_48h": s.events_48h,
            "events_7d": s.events_7d,
            "decay_speed": s.decay_speed,
        }
        rows.append(row)
    return rows


def _session_analytics(runtime_dir: str, *, now_ts: float) -> dict[str, Any]:
    ev = trend_memory_events(runtime_dir, hours=48, now_ts=now_ts)
    sessions: dict[str, list[dict[str, Any]]] = {
        "morning_briefing": [],
        "intraday_signals": [],
        "evening_recap": [],
        "offhours": [],
    }
    for e in ev:
        sessions[_session_key(float(e.get("ts") or 0.0))].append(e)

    def _build(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "events": len(rows),
            "retention": _safe_mean([float(r.get("open_retention") or 0.0) for r in rows]),
            "repost_dynamics": _safe_mean([float(r.get("forward_velocity") or 0.0) for r in rows]),
            "opening_strength": _safe_mean([float(r.get("quoteability") or 0.0) for r in rows]),
            "acceleration": _safe_mean([float(r.get("repost_rate") or 0.0) for r in rows]),
        }

    return {k: _build(v) for k, v in sessions.items()}


def _recommendations(rows: list[dict[str, Any]], sessions: dict[str, Any]) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    for r in rows:
        if float(r["momentum_score"]) >= 0.64 and float(r["repost_velocity"]) >= 0.58:
            recs.append({"action": "increase_frequency", "cluster_key": str(r["cluster_key"]), "reason": "winning_momentum"})
        if float(r["fatigue_probability"]) >= 0.72 or float(r["saturation_level"]) >= 0.85:
            recs.append({"action": "reduce_frequency", "cluster_key": str(r["cluster_key"]), "reason": "fatigue_or_saturation"})
    if float((sessions.get("morning_briefing") or {}).get("retention") or 0.0) < 0.42:
        recs.append({"action": "increase_hook_intensity", "cluster_key": "morning_briefing", "reason": "weak_open_retention"})
    intraday = sessions.get("intraday_signals") or {}
    if float(intraday.get("events") or 0) >= 6 and float(intraday.get("retention") or 0.0) < 0.45:
        recs.append({"action": "reduce_emotional_density", "cluster_key": "intraday_signals", "reason": "volatility_fatigue"})
    return recs[:12]


def _alerts(rows: list[dict[str, Any]], health_score: float) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    if health_score < 0.45:
        alerts.append({"kind": "signal_dilution", "severity": "warning"})
    for r in rows:
        k = str(r["cluster_key"])
        if float(r["saturation_level"]) >= 0.9:
            alerts.append({"kind": "narrative_overheating", "severity": "warning", "cluster_key": k})
        if float(r["fatigue_probability"]) >= 0.78:
            alerts.append({"kind": "feed_fatigue", "severity": "warning", "cluster_key": k})
        if float(r["growth_velocity"]) <= 0.3 and float(r["momentum_score"]) <= 0.35:
            alerts.append({"kind": "momentum_collapse", "severity": "notice", "cluster_key": k})
    return alerts[:20]


def _feed_shape(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"macro_heavy": False, "crypto_heavy": False, "fear_driven": False, "repetitive": False, "dense": False, "reactive": False}
    by = {str(r["cluster_key"]): float(r["signal_density"]) for r in rows}
    macro = by.get("macro_stress", 0.0)
    crypto = by.get("crypto_risk_on", 0.0)
    fear = by.get("geopolitical_escalation", 0.0) + by.get("market_volatility", 0.0)
    repetitive = sum(1 for r in rows if float(r["saturation_level"]) >= 0.72) >= 2
    dense = sum(float(r["events_24h"]) for r in rows) >= 10
    reactive = _safe_mean([float(r["growth_velocity"]) for r in rows]) > 0.7 and _safe_mean(
        [float(r["retention_strength"]) for r in rows]
    ) < 0.45
    return {
        "macro_heavy": macro >= 0.45,
        "crypto_heavy": crypto >= 0.45,
        "fear_driven": fear >= 0.6,
        "repetitive": repetitive,
        "dense": dense,
        "reactive": reactive,
    }


def build_operator_observability_snapshot(runtime_dir: str) -> dict[str, Any]:
    now_ts = time.time()
    rows = _cluster_rows(runtime_dir, now_ts=now_ts)
    winning = [
        r for r in rows if float(r["momentum_score"]) >= 0.62 and float(r["fatigue_probability"]) <= 0.58 and float(r["repost_velocity"]) >= 0.5
    ]
    dying = [r for r in rows if float(r["fatigue_probability"]) >= 0.72 or float(r["decay_speed"]) >= 0.45]
    emerging = [
        r
        for r in rows
        if float(r["growth_velocity"]) >= 0.62 and int(r["events_24h"]) >= 2 and int(r["events_48h"]) <= int(r["events_24h"]) + 2
    ]
    sessions = _session_analytics(runtime_dir, now_ts=now_ts)

    diversity = _clamp(len(rows) / 5.0)
    momentum_avg = _safe_mean([float(r["momentum_score"]) for r in rows])
    fatigue_avg = _safe_mean([float(r["fatigue_probability"]) for r in rows])
    repost_avg = _safe_mean([float(r["repost_velocity"]) for r in rows])
    retention_avg = _safe_mean([float(r["retention_strength"]) for r in rows])
    cadence_stability = _safe_mean([float((sessions.get(k) or {}).get("events") or 0.0) for k in ("morning_briefing", "intraday_signals", "evening_recap")])
    cadence_stability = _clamp(cadence_stability / 4.0)
    health = _clamp(
        diversity * 0.2
        + momentum_avg * 0.22
        + (1.0 - fatigue_avg) * 0.18
        + repost_avg * 0.16
        + retention_avg * 0.16
        + cadence_stability * 0.08
    )
    health = round(health, 4)

    return {
        "generated_at_unix": now_ts,
        "winning_narratives": sorted(winning, key=lambda x: (-float(x["momentum_score"]), -float(x["repost_velocity"])))[:10],
        "dying_narratives": sorted(dying, key=lambda x: (-float(x["fatigue_probability"]), -float(x["decay_speed"])))[:10],
        "emerging_narratives": sorted(emerging, key=lambda x: (-float(x["growth_velocity"]), -int(x["events_24h"])))[:10],
        "narrative_momentum_map": sorted(rows, key=lambda x: (-float(x["momentum_score"]), -float(x["signal_density"]))),
        "fatigue_heatmap": sorted(rows, key=lambda x: -float(x["fatigue_probability"])),
        "repost_leaderboard": sorted(rows, key=lambda x: -float(x["repost_velocity"]))[:12],
        "time_of_day_efficiency": sessions,
        "hashtag_performance": [{"cluster_key": r["cluster_key"], "hashtag_efficiency": r["hashtag_efficiency"]} for r in rows],
        "hook_performance": [{"cluster_key": r["cluster_key"], "open_loop_strength": r["open_loop_strength"], "quoteability_proxy": r["retention_strength"]} for r in rows],
        "signal_quality_trend": {
            "momentum_avg": momentum_avg,
            "fatigue_avg": fatigue_avg,
            "repostability_avg": repost_avg,
            "retention_avg": retention_avg,
        },
        "feed_shape_analysis": _feed_shape(rows),
        "newsroom_health_score": health,
        "adaptive_recommendations": _recommendations(rows, sessions),
        "alerts": _alerts(rows, health),
    }
