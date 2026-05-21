"""Runtime-safe operator editorial controls (auditable, reversible)."""

from __future__ import annotations

import time
from typing import Any

from editorial.governance.ledger import append_decision
from editorial.governance.paths import operator_controls_path
from editorial.intelligence_store import load_json, save_json


def _load(runtime_dir: str | None) -> dict[str, Any]:
    return load_json(
        operator_controls_path(runtime_dir),
        {
            "version": 1,
            "emergency_freeze": False,
            "source_mutes": {},
            "topic_mutes": {},
            "source_boosts": {},
            "topic_boosts": {},
            "source_blocks": {},
        },
    )


def _save(runtime_dir: str | None, data: dict[str, Any]) -> None:
    save_json(operator_controls_path(runtime_dir), data)


def get_operator_controls(runtime_dir: str | None) -> dict[str, Any]:
    return _load(runtime_dir)


def reload_operator_controls(runtime_dir: str | None) -> dict[str, Any]:
    return _load(runtime_dir)


def set_emergency_freeze(runtime_dir: str | None, *, enabled: bool, reason: str = "") -> None:
    data = _load(runtime_dir)
    data["emergency_freeze"] = bool(enabled)
    _save(runtime_dir, data)
    append_decision(
        runtime_dir=runtime_dir,
        decision_type="operator_emergency_freeze",
        outcome="on" if enabled else "off",
        reason_codes=["operator_override"],
        operator_override={"reason": reason[:200], "enabled": enabled},
    )


def is_emergency_freeze(runtime_dir: str | None) -> bool:
    return bool(_load(runtime_dir).get("emergency_freeze"))


def _active_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    until = float(entry.get("until_unix") or 0)
    return until <= 0 or time.time() < until


def mute_source(
    runtime_dir: str | None,
    channel: str,
    *,
    ttl_sec: float = 3600.0,
    reason: str = "",
) -> None:
    key = str(channel or "").strip().lower()
    if not key:
        return
    data = _load(runtime_dir)
    mutes = dict(data.get("source_mutes") or {})
    mutes[key] = {"until_unix": time.time() + max(60.0, ttl_sec), "reason": reason[:200]}
    data["source_mutes"] = mutes
    _save(runtime_dir, data)
    append_decision(
        runtime_dir=runtime_dir,
        decision_type="operator_source_mute",
        outcome="muted",
        subject_type="source",
        subject_id=key,
        operator_override={"ttl_sec": ttl_sec, "reason": reason[:200]},
    )


def mute_topic(
    runtime_dir: str | None,
    topic_key: str,
    *,
    ttl_sec: float = 3600.0,
    reason: str = "",
) -> None:
    key = str(topic_key or "").strip().lower()[:80]
    if not key:
        return
    data = _load(runtime_dir)
    mutes = dict(data.get("topic_mutes") or {})
    mutes[key] = {"until_unix": time.time() + max(60.0, ttl_sec), "reason": reason[:200]}
    data["topic_mutes"] = mutes
    _save(runtime_dir, data)
    append_decision(
        runtime_dir=runtime_dir,
        decision_type="operator_topic_mute",
        outcome="muted",
        subject_type="topic",
        subject_id=key,
        operator_override={"ttl_sec": ttl_sec, "reason": reason[:200]},
    )


def boost_source(runtime_dir: str | None, channel: str, *, boost: float = 0.08, reason: str = "") -> None:
    key = str(channel or "").strip().lower()
    data = _load(runtime_dir)
    boosts = dict(data.get("source_boosts") or {})
    boosts[key] = {"boost": max(-0.2, min(0.25, float(boost))), "reason": reason[:200]}
    data["source_boosts"] = boosts
    _save(runtime_dir, data)
    append_decision(
        runtime_dir=runtime_dir,
        decision_type="operator_source_boost",
        outcome="boost",
        subject_type="source",
        subject_id=key,
        operator_override={"boost": boost, "reason": reason[:200]},
    )


def suppress_source(runtime_dir: str | None, channel: str, *, reason: str = "") -> None:
    key = str(channel or "").strip().lower()
    blocks = dict(_load(runtime_dir).get("source_blocks") or {})
    blocks[key] = {"reason": reason[:200], "ts_unix": time.time()}
    data = _load(runtime_dir)
    data["source_blocks"] = blocks
    _save(runtime_dir, data)
    append_decision(
        runtime_dir=runtime_dir,
        decision_type="operator_source_block",
        outcome="blocked",
        subject_type="source",
        subject_id=key,
        operator_override={"reason": reason[:200]},
    )


def operator_adjustments_for_cluster(
    runtime_dir: str | None,
    *,
    channels: list[str],
    topic_key: str,
) -> tuple[float, list[str], bool]:
    """Return (score_delta, reason_codes, hard_block)."""
    data = _load(runtime_dir)
    if data.get("emergency_freeze"):
        return -1.0, ["emergency_editorial_freeze"], True
    codes: list[str] = []
    delta = 0.0
    topic = str(topic_key or "").strip().lower()
    tm = (data.get("topic_mutes") or {}).get(topic)
    if topic and _active_entry(tm):
        return -1.0, ["operator_topic_muted"], True
    tb = (data.get("topic_boosts") or {}).get(topic)
    if isinstance(tb, dict):
        delta += float(tb.get("boost") or 0)
        codes.append("operator_topic_boost")
    for ch in channels:
        ck = str(ch or "").strip().lower()
        if not ck:
            continue
        if ck in (data.get("source_blocks") or {}):
            return -1.0, ["operator_source_blocked"], True
        sm = (data.get("source_mutes") or {}).get(ck)
        if _active_entry(sm):
            return -1.0, ["operator_source_muted"], True
        sb = (data.get("source_boosts") or {}).get(ck)
        if isinstance(sb, dict):
            delta += float(sb.get("boost") or 0)
            if "operator_source_boost" not in codes:
                codes.append("operator_source_boost")
    return round(delta, 4), codes, False
