"""CCD persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "ccd_state.json"


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "days": {}, "week_counts": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "days": {}, "week_counts": {}}


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_ccd_evaluation(
    runtime_dir: str | None,
    *,
    category: str,
    experience_fit: float,
    binding_score: float,
    spine_matched: bool,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    cats = dict(day.get("category_counts") or {})
    cats[category] = int(cats.get(category) or 0) + 1
    day["category_counts"] = cats

    fits = list(day.get("experience_fits") or [])
    fits.append(float(experience_fit))
    day["experience_fits"] = fits[-200:]

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1
    if not spine_matched:
        day["spine_misses"] = int(day.get("spine_misses") or 0) + 1

    week = dict(data.get("week_counts") or {})
    week[category] = int(week.get(category) or 0) + 1

    days[day_key] = day
    data["days"] = days
    data["week_counts"] = week
    save_state(runtime_dir, data)


def ccd_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    day = dict((data.get("days") or {}).get(day_key) or {})
    fits = [float(x) for x in (day.get("experience_fits") or [])]

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "avg_experience_fit": round(sum(fits) / len(fits), 3) if fits else 0.0,
        "category_counts_today": dict(day.get("category_counts") or {}),
        "week_category_counts": dict(data.get("week_counts") or {}),
        "spine_misses_today": int(day.get("spine_misses") or 0),
        "core_kpis": {
            "weekly_return_rate": "track_via_cohorts",
            "habit_open_rate": "track_via_morning_evening_anchors",
            "evening_wrap_completion_rate": "track_via_engagement_proxy",
            "morning_brief_open_rate": "track_via_engagement_proxy",
            "substitution_rate": "peos_cse",
            "overload_rate": "ccd_persona_simulation",
        },
        "objective": "weekly_cognitive_experience_engine",
    }
