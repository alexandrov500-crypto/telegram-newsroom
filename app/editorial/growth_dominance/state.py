"""Runtime state for EGDL metrics accumulation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "editorial_growth_dominance_state.json"


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "days": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "days": {}}
    data.setdefault("days", {})
    return data


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_gravity_event(
    runtime_dir: str | None,
    *,
    gravity_total: float,
    loop: str,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})
    scores = list(day.get("gravity_scores") or [])
    scores.append(float(gravity_total))
    day["gravity_scores"] = scores[-200:]
    day["posts_evaluated"] = int(day.get("posts_evaluated") or 0) + 1
    if published:
        day["posts_published"] = int(day.get("posts_published") or 0) + 1
    if gravity_total >= 80:
        day["high_gravity_count"] = int(day.get("high_gravity_count") or 0) + 1
    loops = dict(day.get("loop_counts") or {})
    loops[loop] = int(loops.get(loop) or 0) + 1
    day["loop_counts"] = loops
    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def today_gravity_stats(runtime_dir: str | None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    scores = [float(x) for x in (day.get("gravity_scores") or [])]
    avg = sum(scores) / len(scores) if scores else 0.0
    high = int(day.get("high_gravity_count") or 0)
    return {
        "avg_gravity": round(avg, 2),
        "high_gravity_count": high,
        "posts_evaluated": int(day.get("posts_evaluated") or 0),
        "posts_published": int(day.get("posts_published") or 0),
        "loop_counts": dict(day.get("loop_counts") or {}),
    }
