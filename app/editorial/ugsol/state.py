"""UGSOL persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "ugsol_state.json"


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "days": {}, "imri_history": [], "feedback_ema": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "days": {}, "imri_history": [], "feedback_ema": {}}


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def today_format_counts(runtime_dir: str | None) -> dict[str, int]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    return dict(day.get("format_counts") or {})


def record_control_tower_decision(
    runtime_dir: str | None,
    *,
    publish: bool,
    mode: str,
    priority_level: str,
    imri_score: float,
    objective_score: float,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if publish:
        day["approved"] = int(day.get("approved") or 0) + 1
    else:
        day["rejected"] = int(day.get("rejected") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1
        fc = dict(day.get("format_counts") or {})
        fc[mode] = int(fc.get(mode) or 0) + 1
        if priority_level == "flagship":
            fc["flagship"] = int(fc.get("flagship") or 0) + 1
        day["format_counts"] = fc

    scores = list(day.get("objective_scores") or [])
    scores.append(float(objective_score))
    day["objective_scores"] = scores[-200:]

    days[day_key] = day
    data["days"] = days

    history = list(data.get("imri_history") or [])
    history.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "score": imri_score})
    data["imri_history"] = history[-90:]

    save_state(runtime_dir, data)


def ugsol_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    day = dict((data.get("days") or {}).get(day_key) or {})
    scores = [float(x) for x in (day.get("objective_scores") or [])]
    history = list(data.get("imri_history") or [])
    imri_recent = [float(x.get("score") or 0) for x in history[-7:]]

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "approved_today": int(day.get("approved") or 0),
        "published_today": int(day.get("published") or 0),
        "rejected_today": int(day.get("rejected") or 0),
        "avg_objective_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "imri_7d_avg": round(sum(imri_recent) / len(imri_recent), 2) if imri_recent else 0.0,
        "format_counts_today": dict(day.get("format_counts") or {}),
        "objective": "autonomous_cognitive_media_replacement_engine",
    }
