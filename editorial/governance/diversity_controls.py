"""Topic/source balancing, cooldowns, distribution metrics."""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from db.models import RawPost

from editorial.governance.paths import governance_state_path
from editorial.intelligence_store import load_json, save_json


def _state(runtime_dir: str | None) -> dict[str, Any]:
    return load_json(
        governance_state_path(runtime_dir),
        {
            "version": 1,
            "topic_counts": {},
            "source_counts": {},
            "topic_cooldown_until": {},
            "source_cooldown_until": {},
            "suppression_counts": {},
        },
    )


def _save(runtime_dir: str | None, data: dict[str, Any]) -> None:
    save_json(governance_state_path(runtime_dir), data)


def record_selection(
    runtime_dir: str | None,
    *,
    topic_key: str,
    channels: list[str],
) -> None:
    data = _state(runtime_dir)
    tc = Counter(dict(data.get("topic_counts") or {}))
    sc = Counter(dict(data.get("source_counts") or {}))
    tk = str(topic_key or "").strip().lower()[:80]
    if tk:
        tc[tk] += 1
    for ch in channels:
        ck = str(ch or "").strip().lower()
        if ck:
            sc[ck] += 1
    data["topic_counts"] = dict(tc)
    data["source_counts"] = dict(sc)
    _save(runtime_dir, data)


def record_suppression_metric(runtime_dir: str | None, reason: str) -> None:
    data = _state(runtime_dir)
    sc = Counter(dict(data.get("suppression_counts") or {}))
    sc[str(reason or "unknown")[:60]] += 1
    data["suppression_counts"] = dict(sc)
    _save(runtime_dir, data)


def apply_cooldowns(
    runtime_dir: str | None,
    *,
    topic_key: str,
    channels: list[str],
    topic_cap: int = 5,
    source_cap: int = 8,
    cooldown_sec: float = 900.0,
) -> tuple[bool, list[str]]:
    """Return (blocked, reason_codes) if topic or dominant source on cooldown."""
    try:
        from app.editorial.wire_recovery import wire_bypass_diversity_cooldowns

        if wire_bypass_diversity_cooldowns():
            return False, []
    except Exception:
        pass
    data = _state(runtime_dir)
    now = time.time()
    codes: list[str] = []
    tk = str(topic_key or "").strip().lower()[:80]
    tc = dict(data.get("topic_counts") or {})
    if tk and int(tc.get(tk) or 0) >= topic_cap:
        until = dict(data.get("topic_cooldown_until") or {})
        until[tk] = now + cooldown_sec
        data["topic_cooldown_until"] = until
        _save(runtime_dir, data)
        codes.append("topic_cooldown")
    tu = dict(data.get("topic_cooldown_until") or {})
    if tk and float(tu.get(tk) or 0) > now:
        codes.append("topic_on_cooldown")
    scounts = dict(data.get("source_counts") or {})
    for ch in channels:
        ck = str(ch or "").strip().lower()
        if ck and int(scounts.get(ck) or 0) >= source_cap:
            su = dict(data.get("source_cooldown_until") or {})
            su[ck] = now + cooldown_sec
            data["source_cooldown_until"] = su
            _save(runtime_dir, data)
            codes.append("source_cooldown")
    su_map = dict(data.get("source_cooldown_until") or {})
    for ch in channels:
        ck = str(ch or "").strip().lower()
        if ck and float(su_map.get(ck) or 0) > now:
            codes.append("source_on_cooldown")
    blocked = "topic_on_cooldown" in codes or "source_on_cooldown" in codes
    return blocked, codes


def diversity_metrics(runtime_dir: str | None) -> dict[str, Any]:
    data = _state(runtime_dir)
    tc = dict(data.get("topic_counts") or {})
    sc = dict(data.get("source_counts") or {})
    total_t = sum(tc.values()) or 1
    total_s = sum(sc.values()) or 1
    topic_dist = {k: round(v / total_t, 4) for k, v in sorted(tc.items(), key=lambda x: -x[1])[:20]}
    source_dist = {k: round(v / total_s, 4) for k, v in sorted(sc.items(), key=lambda x: -x[1])[:20]}
    return {
        "topic_distribution": topic_dist,
        "source_distribution": source_dist,
        "suppression_counts": dict(data.get("suppression_counts") or {}),
    }
