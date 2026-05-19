from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state

MAX_ENTRIES = 20


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _evict(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(entries) <= MAX_ENTRIES:
        return entries
    return sorted(entries, key=lambda e: str(e.get("recorded_day", "")), reverse=True)[:MAX_ENTRIES]


def touch_legacy_memory(
    *,
    dependency_risk: str = "LOW",
    succession_safe: bool = False,
    explainability_gap: bool = False,
) -> dict[str, Any]:
    """Bounded stewardship continuity memory — no human profiling."""
    today = _utc_day()
    try:
        st = load_state()
        mem: dict[str, Any] = dict(st.get("legacy_memory") or {})
        entries: list[dict[str, Any]] = list(mem.get("entries") or [])
        touch = dict(mem.get("touch") or {})

        if touch.get("day") != today:
            if dependency_risk in ("MODERATE", "HIGH"):
                entries.append(
                    {
                        "kind": "dependency_episode",
                        "recorded_day": today,
                        "risk": dependency_risk,
                    },
                )
            if succession_safe:
                entries.append(
                    {
                        "kind": "succession_safe_calm",
                        "recorded_day": today,
                    },
                )
            if explainability_gap:
                entries.append(
                    {
                        "kind": "explainability_gap",
                        "recorded_day": today,
                    },
                )
            touch["day"] = today

        entries = _evict(entries)
        mem["entries"] = entries
        mem["touch"] = touch
        save_state(metrics={"legacy_memory": mem})
        return mem
    except Exception:
        return {}
