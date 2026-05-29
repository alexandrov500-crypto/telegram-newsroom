"""Stateful trend memory for narrative momentum and fatigue."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from app.editorial.growth_cadence import resolve_cadence_session

_LOCK = threading.RLock()
_MAX_EVENTS = 2500

_AI_CLUSTER = re.compile(
    r"(nvidia|openai|\bai\b|(?:^|[\s,.:;«»])ии(?:[\s,.:;»]|$)|"
    r"искусственн\w*\s+интеллект|chip|semiconductor|hyperscaler|capex)",
    re.I,
)
_MACRO_CLUSTER = re.compile(r"(fed|fomc|rates?|yield|inflation|cpi|pce|bond|ставк|инфляц|доходност)", re.I)
_GEO_CLUSTER = re.compile(r"(china|usa|russia|middle\s*east|sanction|oil|shipping|military|геополит|санкци)", re.I)
_CRYPTO_CLUSTER = re.compile(r"(bitcoin|btc|ethereum|eth|etf|altseason|crypto|крипт|on-?chain)", re.I)
_VOL_CLUSTER = re.compile(r"(volatility|crash|rally|liq|panic|selloff|vol)", re.I)


@dataclass(frozen=True)
class ClusterSnapshot:
    cluster_key: str
    repost_rate: float
    forward_velocity: float
    open_retention: float
    reaction_density: float
    quoteability: float
    screenshot_probability: float
    engagement_longevity: float
    recurrence_frequency: float
    narrative_momentum: float
    decay_speed: float
    momentum_score: float
    growth_velocity: float
    saturation_level: float
    fatigue_probability: float
    events_24h: int
    events_48h: int
    events_7d: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _path(runtime_dir: str) -> Path:
    p = Path(runtime_dir).expanduser().resolve() / "editorial" / "trend_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _default_state() -> dict[str, Any]:
    return {"version": 1, "events": []}


def _load(runtime_dir: str) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return _default_state()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def _save(runtime_dir: str, data: dict[str, Any]) -> None:
    _path(runtime_dir).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def trend_memory_snapshot(runtime_dir: str) -> dict[str, Any]:
    with _LOCK:
        return _load(runtime_dir)


def trend_memory_events(runtime_dir: str, *, hours: float | None = None, now_ts: float | None = None) -> list[dict[str, Any]]:
    now = float(now_ts if now_ts is not None else time.time())
    with _LOCK:
        state = _load(runtime_dir)
    events = [e for e in (state.get("events") or []) if isinstance(e, dict)]
    if hours is None:
        return events
    cutoff = now - float(hours) * 3600.0
    return [e for e in events if float(e.get("ts") or 0.0) >= cutoff]


def infer_narrative_cluster(text: str, *, category: str = "") -> str:
    t = (text or "").strip()
    c = (category or "").strip().lower()
    if _AI_CLUSTER.search(t):
        return "ai_boom"
    if _MACRO_CLUSTER.search(t) or c == "macro":
        return "macro_stress"
    if _GEO_CLUSTER.search(t) or c == "geo":
        return "geopolitical_escalation"
    if _CRYPTO_CLUSTER.search(t) or c == "crypto":
        return "crypto_risk_on"
    if _VOL_CLUSTER.search(t) or c == "market":
        return "market_volatility"
    return "general_market"


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    vals: list[float] = []
    for r in rows:
        try:
            vals.append(float(r.get(key) or 0.0))
        except (TypeError, ValueError):
            continue
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)


def _window(rows: list[dict[str, Any]], *, now: float, sec: float) -> list[dict[str, Any]]:
    cutoff = now - sec
    return [r for r in rows if float(r.get("ts") or 0.0) >= cutoff]


def _window_between(rows: list[dict[str, Any]], *, now: float, start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    low = now - end_sec
    high = now - start_sec
    return [r for r in rows if low <= float(r.get("ts") or 0.0) < high]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def cluster_snapshot(runtime_dir: str, *, cluster_key: str, now: float | None = None) -> ClusterSnapshot:
    now_ts = now if now is not None else time.time()
    with _LOCK:
        state = _load(runtime_dir)
    events = [e for e in (state.get("events") or []) if isinstance(e, dict) and e.get("cluster_key") == cluster_key]
    e24 = _window(events, now=now_ts, sec=24 * 3600)
    e48 = _window(events, now=now_ts, sec=48 * 3600)
    e7 = _window(events, now=now_ts, sec=7 * 24 * 3600)
    prev24 = _window_between(events, now=now_ts, start_sec=24 * 3600, end_sec=48 * 3600)

    repost = _avg(e24, "repost_rate")
    forward = _avg(e24, "forward_velocity")
    retention = _avg(e24, "open_retention")
    reaction = _avg(e24, "reaction_density")
    quote = _avg(e24, "quoteability")
    screenshot = _avg(e24, "screenshot_probability")
    longevity = _avg(e48, "engagement_longevity")
    rec_freq = round(len(e7) / 7.0, 4)

    now_mix = (repost * 0.3 + forward * 0.2 + retention * 0.2 + reaction * 0.12 + quote * 0.1 + screenshot * 0.08)
    prev_mix = (
        _avg(prev24, "repost_rate") * 0.3
        + _avg(prev24, "forward_velocity") * 0.2
        + _avg(prev24, "open_retention") * 0.2
        + _avg(prev24, "reaction_density") * 0.12
        + _avg(prev24, "quoteability") * 0.1
        + _avg(prev24, "screenshot_probability") * 0.08
    )
    momentum = round(_clamp(0.5 + (now_mix - prev_mix) * 1.6, 0.0, 1.0), 4)
    growth_velocity = round(_clamp(0.5 + ((len(e24) - len(prev24)) / max(1.0, len(prev24) + 1.0)) * 0.8), 4)
    saturation = round(_clamp(len(e24) / 6.0), 4)
    decay = round(_clamp(max(0.0, prev_mix - now_mix) * 1.8), 4)
    fatigue = round(_clamp(saturation * 0.45 + decay * 0.35 + (0.25 if forward < 0.45 else 0.0)), 4)
    momentum_score = round(_clamp(momentum * 0.55 + growth_velocity * 0.45), 4)

    return ClusterSnapshot(
        cluster_key=cluster_key,
        repost_rate=repost,
        forward_velocity=forward,
        open_retention=retention,
        reaction_density=reaction,
        quoteability=quote,
        screenshot_probability=screenshot,
        engagement_longevity=longevity,
        recurrence_frequency=rec_freq,
        narrative_momentum=momentum,
        decay_speed=decay,
        momentum_score=momentum_score,
        growth_velocity=growth_velocity,
        saturation_level=saturation,
        fatigue_probability=fatigue,
        events_24h=len(e24),
        events_48h=len(e48),
        events_7d=len(e7),
    )


def evaluate_narrative_strategy(
    runtime_dir: str,
    *,
    text: str,
    category: str = "",
    now_ts: float | None = None,
) -> dict[str, Any]:
    cluster_key = infer_narrative_cluster(text, category=category)
    snap = cluster_snapshot(runtime_dir, cluster_key=cluster_key, now=now_ts)
    pm = _clamp(1.0 + (snap.momentum_score - 0.5) * 0.28 - (snap.fatigue_probability - 0.5) * 0.24, 0.82, 1.22)
    status = "stable"
    if snap.momentum_score >= 0.62 and snap.fatigue_probability <= 0.58:
        status = "winning"
    elif snap.fatigue_probability >= 0.72 and snap.momentum_score <= 0.48:
        status = "dying"
    return {
        "cluster_key": cluster_key,
        "momentum_score": snap.momentum_score,
        "growth_velocity": snap.growth_velocity,
        "saturation_level": snap.saturation_level,
        "fatigue_probability": snap.fatigue_probability,
        "narrative_momentum": snap.narrative_momentum,
        "decay_speed": snap.decay_speed,
        "events_24h": snap.events_24h,
        "events_48h": snap.events_48h,
        "events_7d": snap.events_7d,
        "priority_multiplier": round(pm, 4),
        "status": status,
        "hashtag_persistence": status == "winning",
        "open_loop_continuation": status != "dying",
        "posting_frequency_bias": "up" if status == "winning" else "down" if status == "dying" else "hold",
    }


def observe_narrative_event(
    runtime_dir: str,
    *,
    text: str,
    category: str = "",
    repost_rate: float = 0.0,
    forward_velocity: float = 0.0,
    open_retention: float = 0.0,
    reaction_density: float = 0.0,
    quoteability: float = 0.0,
    screenshot_probability: float = 0.0,
    engagement_longevity: float = 0.0,
    hashtags: list[str] | None = None,
    hook_variant: str = "",
    now_ts: float | None = None,
) -> dict[str, Any]:
    ts = float(now_ts if now_ts is not None else time.time())
    cluster_key = infer_narrative_cluster(text, category=category)
    row = {
        "ts": ts,
        "cluster_key": cluster_key,
        "repost_rate": _clamp(float(repost_rate)),
        "forward_velocity": _clamp(float(forward_velocity)),
        "open_retention": _clamp(float(open_retention)),
        "reaction_density": _clamp(float(reaction_density)),
        "quoteability": _clamp(float(quoteability)),
        "screenshot_probability": _clamp(float(screenshot_probability)),
        "engagement_longevity": _clamp(float(engagement_longevity)),
        "hashtags": [str(t) for t in (hashtags or [])][:5],
        "hook_variant": (hook_variant or "")[:64],
    }
    with _LOCK:
        state = _load(runtime_dir)
        events = [e for e in (state.get("events") or []) if isinstance(e, dict)]
        events.append(row)
        if len(events) > _MAX_EVENTS:
            events = events[-_MAX_EVENTS:]
        state["events"] = events
        state["version"] = 1
        _save(runtime_dir, state)
    return evaluate_narrative_strategy(runtime_dir, text=text, category=category, now_ts=ts)


def choose_hashtags(
    runtime_dir: str,
    *,
    cluster_key: str,
    candidates: list[str],
    limit: int = 3,
    now_ts: float | None = None,
) -> list[str]:
    now = float(now_ts if now_ts is not None else time.time())
    with _LOCK:
        state = _load(runtime_dir)
    events = [e for e in (state.get("events") or []) if isinstance(e, dict) and float(e.get("ts") or 0) >= now - 7 * 86400]
    tag_score: dict[str, float] = {}
    for e in events:
        tags = [str(t) for t in (e.get("hashtags") or [])]
        if not tags:
            continue
        perf = (
            float(e.get("repost_rate") or 0.0) * 0.35
            + float(e.get("forward_velocity") or 0.0) * 0.25
            + float(e.get("quoteability") or 0.0) * 0.2
            + float(e.get("screenshot_probability") or 0.0) * 0.2
        )
        if str(e.get("cluster_key") or "") == cluster_key:
            perf *= 1.15
        for t in tags:
            tag_score[t] = max(tag_score.get(t, 0.0), perf)
    ordered = sorted({str(t) for t in candidates}, key=lambda t: (-tag_score.get(t, 0.0), t))
    return ordered[: max(1, min(3, int(limit)))]


def time_of_day_cluster_fit(runtime_dir: str, *, cluster_key: str) -> float:
    _ = runtime_dir
    sess = resolve_cadence_session()
    if sess.key == "morning_briefing":
        pref = {"macro_stress": 1.0, "general_market": 0.8, "market_volatility": 0.75}
    elif sess.key == "intraday_signals":
        pref = {"market_volatility": 1.0, "ai_boom": 0.92, "geopolitical_escalation": 0.9, "crypto_risk_on": 0.88}
    elif sess.key == "evening_recap":
        pref = {"general_market": 1.0, "macro_stress": 0.88, "ai_boom": 0.82}
    else:
        pref = {"market_volatility": 0.82, "crypto_risk_on": 0.86}
    return float(pref.get(cluster_key, 0.72))
