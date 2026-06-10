"""EAA v2 persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "eaa_state.json"


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


def record_eaa_decision(
    runtime_dir: str | None,
    *,
    mode: str,
    autonomous_publish: bool,
    confidence: float,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})
    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if autonomous_publish:
        day["autonomous_approved"] = int(day.get("autonomous_approved") or 0) + 1
    if mode == "zero_human":
        day["zero_human"] = int(day.get("zero_human") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1
    confs = list(day.get("confidences") or [])
    confs.append(float(confidence))
    day["confidences"] = confs[-100:]
    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def eaa_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    confs = [float(x) for x in (day.get("confidences") or [])]
    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "autonomous_approved_today": int(day.get("autonomous_approved") or 0),
        "zero_human_today": int(day.get("zero_human") or 0),
        "avg_confidence": round(sum(confs) / len(confs), 3) if confs else 0.0,
        "objective": "editorial_ai_autonomy_v2",
    }
