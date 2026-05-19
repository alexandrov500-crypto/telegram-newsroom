from __future__ import annotations

from collections import defaultdict
from typing import Any


def evaluate_recovery_quality(recovery_log: list[dict[str, Any]]) -> dict[str, Any]:
    """Recovery reliability metrics — not just counts."""
    if not recovery_log:
        return {
            "total": 0,
            "successful": 0,
            "repeated": 0,
            "ineffective": 0,
            "recovery_storm": False,
            "mean_duration_sec": None,
            "by_subsystem": {},
        }

    by_sub: dict[str, list[dict[str, Any]]] = defaultdict(list)
    durations: list[float] = []
    successful = 0
    repeated = 0
    ineffective = 0

    for row in recovery_log:
        sub = str(row.get("subsystem") or "runtime")
        by_sub[sub].append(row)
        outcome = str(row.get("outcome") or "")
        if outcome in ("success", "cleared", "recovered"):
            successful += 1
        elif outcome == "repeated":
            repeated += 1
        elif outcome in ("failed", "ineffective", "no_effect"):
            ineffective += 1
        dur = row.get("duration_sec")
        if dur is not None:
            durations.append(float(dur))

    storm = False
    for sub, rows in by_sub.items():
        if len(rows) >= 4:
            recent = rows[:4]
            if sum(1 for r in recent if r.get("outcome") == "repeated") >= 3:
                storm = True

    mean_dur = sum(durations) / len(durations) if durations else None
    sub_summary = {}
    for sub, rows in by_sub.items():
        sub_summary[sub] = {
            "attempts": len(rows),
            "successful": sum(1 for r in rows if r.get("outcome") in ("success", "cleared", "recovered")),
        }

    return {
        "total": len(recovery_log),
        "successful": successful,
        "repeated": repeated,
        "ineffective": ineffective,
        "recovery_storm": storm or (repeated >= 3 and len(recovery_log) >= 5),
        "mean_duration_sec": round(mean_dur, 2) if mean_dur is not None else None,
        "by_subsystem": sub_summary,
    }
