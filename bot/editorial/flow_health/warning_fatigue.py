from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state

TIERS = ("INFO", "NOTICE", "WARNING", "CRITICAL")
_TIER_RANK = {t: i for i, t in enumerate(TIERS)}


def _warning_id(message: str, category: str) -> str:
    h = hashlib.sha256(f"{category}:{message}".encode()).hexdigest()[:16]
    return h


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_warning_event(warning_id: str, *, tier: str, message: str) -> None:
    try:
        st = load_state()
        hist: dict[str, Any] = dict(st.get("warning_history") or {})
        entry = dict(hist.get(warning_id) or {})
        entry["tier"] = tier
        entry["message"] = message[:200]
        entry["count"] = int(entry.get("count") or 0) + 1
        entry["last_seen"] = _utcnow().isoformat()
        entry.setdefault("first_seen", entry["last_seen"])
        hist[warning_id] = entry
        if len(hist) > 80:
            oldest = sorted(hist.items(), key=lambda x: x[1].get("last_seen", ""))[:20]
            for k, _ in oldest:
                hist.pop(k, None)
        save_state(metrics={"warning_history": hist})
    except Exception:
        pass


def process_warnings(raw_warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse repetitive low-tier warnings; escalate chronic or worsening issues.
    """
    if os.getenv("WARNING_FATIGUE_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return raw_warnings

    try:
        collapse_after = int(os.getenv("WARNING_COLLAPSE_AFTER", "3"))
    except ValueError:
        collapse_after = 3
    try:
        expire_hours = float(os.getenv("WARNING_EXPIRE_HOURS", "36"))
    except ValueError:
        expire_hours = 36.0

    st = load_state()
    hist: dict[str, Any] = dict(st.get("warning_history") or {})
    out: list[dict[str, Any]] = []
    collapsed_categories: dict[str, int] = {}

    for w in raw_warnings:
        tier = str(w.get("tier", "NOTICE")).upper()
        if tier not in _TIER_RANK:
            tier = "NOTICE"
        msg = str(w.get("message", ""))[:200]
        cat = str(w.get("category", "general"))
        wid = w.get("id") or _warning_id(msg, cat)
        record_warning_event(wid, tier=tier, message=msg)

        entry = hist.get(wid) or {}
        count = int(entry.get("count") or 1)
        prev_tier = str(entry.get("tier") or tier)

        if tier == "INFO" and count >= collapse_after:
            collapsed_categories[cat] = collapsed_categories.get(cat, 0) + 1
            continue

        if _TIER_RANK.get(tier, 0) < _TIER_RANK.get(prev_tier, 0) and count >= collapse_after:
            tier = prev_tier

        if count >= collapse_after + 2 and tier in ("NOTICE", "WARNING"):
            tier = "WARNING" if tier == "NOTICE" else "CRITICAL"
            msg = f"{msg} (persistent ×{count})"

        out.append({"id": wid, "tier": tier, "message": msg, "category": cat, "count": count})

    for cat, n in collapsed_categories.items():
        out.append(
            {
                "id": _warning_id(f"collapsed:{cat}", cat),
                "tier": "NOTICE",
                "message": f"Recurring {cat} advisories collapsed ({n} suppressed)",
                "category": cat,
                "count": n,
                "collapsed": True,
            },
        )

    cutoff = _utcnow() - timedelta(hours=expire_hours)
    filtered: list[dict[str, Any]] = []
    for w in out:
        wid = w.get("id")
        entry = hist.get(wid) or {}
        try:
            last = datetime.fromisoformat(str(entry.get("last_seen", "")).replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except ValueError:
            filtered.append(w)
            continue
        if w.get("tier") == "CRITICAL" or last >= cutoff:
            filtered.append(w)

    filtered.sort(key=lambda x: _TIER_RANK.get(str(x.get("tier")), 0), reverse=True)
    return filtered[: int(os.getenv("WARNING_DIGEST_MAX", "6"))]
