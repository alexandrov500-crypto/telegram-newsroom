"""Observable state for AUH metrics (distribution tracking)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "audience_unification_state.json"


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "days": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "days": {}}


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_auh_evaluation(
    runtime_dir: str | None,
    *,
    ues: float,
    crs: float,
    reader_relevance: float,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})
    for key, val in (
        ("ues_scores", ues),
        ("crs_scores", crs),
        ("reader_relevance_scores", reader_relevance),
    ):
        arr = list(day.get(key) or [])
        arr.append(float(val))
        day[key] = arr[-300:]
    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1
    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def auh_distribution_snapshot(runtime_dir: str | None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})

    def _avg(key: str) -> float:
        vals = [float(x) for x in (day.get(key) or [])]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    ues_vals = [float(x) for x in (day.get("ues_scores") or [])]
    crs_vals = [float(x) for x in (day.get("crs_scores") or [])]
    rel_vals = [float(x) for x in (day.get("reader_relevance_scores") or [])]

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "ues_avg": _avg("ues_scores"),
        "crs_avg": _avg("crs_scores"),
        "reader_relevance_avg": _avg("reader_relevance_scores"),
        "pct_ues_gte_82": round(sum(1 for v in ues_vals if v >= 82) / max(1, len(ues_vals)) * 100, 1),
        "pct_crs_gte_70": round(sum(1 for v in crs_vals if v >= 70) / max(1, len(crs_vals)) * 100, 1),
        "objective": "maximize_cross_source_cognitive_replacement_per_user",
    }
