from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_reliability_timeline(
    historical: list[dict[str, Any]],
    *,
    windows: tuple[int, ...] = (7, 30),
) -> dict[str, Any]:
    """Track subsystem reliability over 7d / 30d windows."""
    by_sub: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in historical:
        sub = str(row.get("subsystem") or "")
        metrics = row.get("metrics") or {}
        rel = metrics.get("reliability")
        if sub and rel is not None:
            by_sub[sub].append((str(row.get("date") or ""), float(rel)))

    timeline: dict[str, Any] = {"windows": {}, "direction": "insufficient_data"}
    for days in windows:
        window_data: dict[str, dict[str, float | None]] = {}
        for sub, points in by_sub.items():
            recent = [p[1] for p in points[:days] if p[1] is not None]
            prior = [p[1] for p in points[days : days * 2] if p[1] is not None]
            cur_avg = sum(recent) / len(recent) if recent else None
            prior_avg = sum(prior) / len(prior) if prior else None
            delta = None
            if cur_avg is not None and prior_avg is not None:
                delta = round(cur_avg - prior_avg, 3)
            window_data[sub] = {
                "current_avg": round(cur_avg, 3) if cur_avg is not None else None,
                "prior_avg": round(prior_avg, 3) if prior_avg is not None else None,
                "delta": delta,
            }
        timeline["windows"][f"{days}d"] = window_data

    all_deltas: list[float] = []
    w7 = timeline["windows"].get("7d") or {}
    for m in w7.values():
        if m.get("delta") is not None:
            all_deltas.append(float(m["delta"]))
    if not all_deltas:
        timeline["direction"] = "insufficient_data"
    elif sum(all_deltas) / len(all_deltas) > 0.04:
        timeline["direction"] = "improving"
    elif sum(all_deltas) / len(all_deltas) < -0.04:
        timeline["direction"] = "degrading"
    else:
        timeline["direction"] = "stable"

    return timeline
