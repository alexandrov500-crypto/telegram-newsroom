from __future__ import annotations

from typing import Any


def update_baseline(existing: dict[str, Any], pulse: dict[str, Any]) -> dict[str, Any]:
    """Rolling min/max/avg for key metrics during observation phase."""
    if not existing:
        existing = {
            "pulse_count": 0,
            "event_loop_lag_max": {"min": None, "max": None, "last": None},
            "publishes_this_hour": {"max": 0},
            "published_24h": {"max": 0},
        }

    existing["pulse_count"] = int(existing.get("pulse_count", 0)) + 1
    existing["last_updated"] = pulse.get("timestamp")
    existing["runtime_instance_id"] = pulse.get("runtime_instance_id")

    lag = float(pulse.get("event_loop_lag_max") or 0.0)
    lag_box = existing.setdefault("event_loop_lag_max", {})
    lag_box["last"] = lag
    lag_box["max"] = lag if lag_box.get("max") is None else max(float(lag_box["max"]), lag)
    lag_box["min"] = lag if lag_box.get("min") is None else min(float(lag_box["min"]), lag)

    pub_h = int(pulse.get("publishes_this_hour") or 0)
    pub_box = existing.setdefault("publishes_this_hour", {})
    pub_box["max"] = max(int(pub_box.get("max", 0)), pub_h)

    p24 = int((pulse.get("publish_stats_24h") or {}).get("published_24h") or 0)
    p24_box = existing.setdefault("published_24h", {})
    p24_box["max"] = max(int(p24_box.get("max", 0)), p24)

    existing["last_severity"] = pulse.get("severity")
    return existing
