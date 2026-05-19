from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state

MAX_ENTRIES = 25


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _evict(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(entries) <= MAX_ENTRIES:
        return entries
    return sorted(entries, key=lambda e: str(e.get("recorded_day", "")), reverse=True)[:MAX_ENTRIES]


def touch_sustainability_memory(
    *,
    erosion: dict[str, Any] | None = None,
    resilience: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded strategic_resilience_memory — no timeline replay."""
    eros = erosion or {}
    res = resilience or {}
    doc = doctrine or {}
    omem = operational_memory or {}
    today = _utc_day()

    try:
        st = load_state()
        mem: dict[str, Any] = dict(st.get("strategic_resilience_memory") or {})
        entries: list[dict[str, Any]] = list(mem.get("entries") or [])
        touch = dict(mem.get("touch") or {})

        if touch.get("day") != today:
            if eros.get("architectural_erosion_detected"):
                entries.append(
                    {
                        "kind": "erosion_episode",
                        "recorded_day": today,
                        "signals": (eros.get("erosion_signals") or [])[:4],
                    },
                )
            if res.get("strategic_resilience_band") in ("RESILIENT", "LONG_HORIZON"):
                entries.append(
                    {
                        "kind": "calm_continuity",
                        "recorded_day": today,
                        "band": res.get("strategic_resilience_band"),
                    },
                )
            if omem.get("recurrence_detected"):
                entries.append(
                    {
                        "kind": "intervention_cycle",
                        "recorded_day": today,
                        "signatures": (omem.get("recurrence") or {}).get("recurrence_signatures") or [],
                    },
                )
            if doc.get("doctrine_drift_detected"):
                entries.append(
                    {
                        "kind": "doctrine_degradation_window",
                        "recorded_day": today,
                    },
                )
            if (omem.get("recovery_pattern") or {}).get("recovery_quality_improving"):
                entries.append(
                    {
                        "kind": "sustainability_recovery",
                        "recorded_day": today,
                        "mode": omem.get("historical_recovery_mode"),
                    },
                )
            touch["day"] = today

        entries = _evict(entries)
        mem["entries"] = entries
        mem["touch"] = touch
        save_state(metrics={"strategic_resilience_memory": mem})
        return mem
    except Exception:
        return {}
