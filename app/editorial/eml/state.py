"""EML persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "eml_state.json"


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


def record_eml_evaluation(
    runtime_dir: str | None,
    *,
    cognitive_value: float,
    value_index: float,
    monetization_allowed: bool,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})
    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if monetization_allowed:
        day["monetization_eligible"] = int(day.get("monetization_eligible") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1
    vals = list(day.get("cognitive_values") or [])
    vals.append(float(cognitive_value))
    day["cognitive_values"] = vals[-100:]
    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def eml_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    vals = [float(x) for x in (day.get("cognitive_values") or [])]
    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "monetization_eligible_today": int(day.get("monetization_eligible") or 0),
        "avg_cognitive_value": round(sum(vals) / len(vals), 3) if vals else 0.0,
        "objective": "attention_to_value_to_revenue_abstraction",
    }
