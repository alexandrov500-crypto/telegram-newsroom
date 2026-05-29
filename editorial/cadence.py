"""Publication cadence: pacing, quiet hours, burst smoothing (no external scheduler)."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from editorial.intelligence_store import cadence_state_path, load_json, save_json
from editorial.policy_models import ChannelEditorialPolicy


def topic_dedupe_key(topic_hint: str) -> str:
    h = " ".join((topic_hint or "").lower().split())[:200]
    return hashlib.sha256(h.encode("utf-8", errors="ignore")).hexdigest()[:20]


def _local_hour(settings: Any, now_unix: float | None = None) -> int:
    tz_name = str(getattr(settings, "newsroom_timezone", "UTC") or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    ts = float(now_unix or time.time())
    dt = datetime.fromtimestamp(ts, tz=tz)
    return int(dt.hour)


def _in_quiet_hours(policy: ChannelEditorialPolicy, settings: Any, now_unix: float | None = None) -> bool:
    if not policy.quiet_hours_local:
        return False
    h = _local_hour(settings, now_unix)
    for start, end in policy.quiet_hours_local:
        if start <= end:
            if start <= h <= end:
                return True
        else:
            if h >= start or h <= end:
                return True
    return False


def _load_state(runtime_dir: str | None) -> dict[str, Any]:
    return load_json(cadence_state_path(runtime_dir), {"version": 1, "last_publish_unix": 0.0, "recent": []})


def _save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    save_json(cadence_state_path(runtime_dir), data)


def record_publish(runtime_dir: str | None, *, topic_key: str = "") -> None:
    data = _load_state(runtime_dir)
    now = time.time()
    data["last_publish_unix"] = now
    recent = list(data.get("recent") or [])
    recent.insert(0, {"ts": now, "topic_key": str(topic_key)[:120]})
    data["recent"] = recent[:80]
    _save_state(runtime_dir, data)


def cadence_should_defer_cluster(
    settings: Any,
    runtime_dir: str | None,
    policy: ChannelEditorialPolicy,
    *,
    topic_key: str,
    urgency: bool,
    now_unix: float | None = None,
) -> tuple[bool, list[str]]:
    """
    Defer non-urgent summarization tick when publish-side cadence is hot (burst smoothing).
    Does not persist per-cluster; operator inspectable via reasons.
    """
    reasons: list[str] = []
    if urgency:
        return False, reasons
    now = float(now_unix or time.time())
    data = _load_state(runtime_dir)
    last = float(data.get("last_publish_unix") or 0.0)
    min_gap = float(policy.min_publish_interval_sec or getattr(settings, "publish_channel_min_interval_sec", 0.0) or 0.0)
    if min_gap > 0 and last > 0 and (now - last) < min_gap * 0.35:
        reasons.append("cadence_recent_publish_gap_short")
        return True, reasons
    recent = list(data.get("recent") or [])[:24]
    same_topic = sum(1 for r in recent if isinstance(r, dict) and str(r.get("topic_key") or "") == topic_key[:120])
    if same_topic >= 4 and not urgency:
        reasons.append("cadence_repeated_topic_recent")
        return True, reasons
    if _in_quiet_hours(policy, settings, now_unix=now) and not urgency:
        reasons.append("cadence_quiet_hours")
        return True, reasons
    return False, reasons


def evaluate_publish_gate(
    settings: Any,
    runtime_dir: str | None,
    policy: ChannelEditorialPolicy,
    *,
    topic_key: str,
    is_breaking: bool,
    now_unix: float | None = None,
    content: str = "",
) -> tuple[bool, list[str]]:
    """
    Returns (block_publish, reasons). When block_publish is True, caller should not approve/send yet.
    """
    reasons: list[str] = []
    if is_breaking:
        return False, reasons
    now = float(now_unix or time.time())
    if _in_quiet_hours(policy, settings, now_unix=now):
        reasons.append("publish_gate_quiet_hours")
        return True, reasons
    min_gap = float(policy.min_publish_interval_sec or getattr(settings, "publish_channel_min_interval_sec", 0.0) or 0.0)
    data = _load_state(runtime_dir)
    last = float(data.get("last_publish_unix") or 0.0)
    if min_gap > 0 and last > 0 and (now - last) < min_gap:
        reasons.append("publish_gate_min_interval")
        return True, reasons
    burst_win = float(getattr(settings, "publish_burst_window_sec", 120.0) or 120.0)
    burst_max = int(getattr(settings, "publish_burst_max_messages", 4) or 4)
    recent = [float(r.get("ts") or 0) for r in (data.get("recent") or []) if isinstance(r, dict)]
    recent = [t for t in recent if now - t <= burst_win]
    if len(recent) >= burst_max:
        reasons.append("publish_gate_burst_cap")
        return True, reasons

    from app.editorial.cadence_intelligence import evaluate_cadence_intelligence

    intel_block, intel_reasons = evaluate_cadence_intelligence(
        settings,
        runtime_dir,
        content=content or topic_key,
        topic_key=topic_key,
        is_breaking=is_breaking,
        now_unix=now,
    )
    if intel_block:
        reasons.extend(intel_reasons)
        return True, reasons

    try:
        from app.growth.cadence_engine import evaluate_growth_cadence_gate

        growth = evaluate_growth_cadence_gate(
            settings,
            runtime_dir,
            topic_key=topic_key,
            content=content or topic_key,
            is_breaking=is_breaking,
            now_unix=now,
        )
        if growth.block:
            reasons.extend(growth.reasons)
            return True, reasons
    except Exception:
        pass

    return False, reasons
