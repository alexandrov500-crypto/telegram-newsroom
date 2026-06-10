"""GMCS persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "gmcs_state.json"


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "days": {}, "mdi_history": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "days": {}, "mdi_history": []}


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_gmcs_evaluation(
    runtime_dir: str | None,
    *,
    mdi: float,
    channels_substituted: int,
    vertical: str,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})
    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1
    mdis = list(day.get("mdi_scores") or [])
    mdis.append(float(mdi))
    day["mdi_scores"] = mdis[-100:]
    verts = dict(day.get("vertical_wins") or {})
    verts[vertical] = int(verts.get(vertical) or 0) + channels_substituted
    day["vertical_wins"] = verts
    days[day_key] = day
    data["days"] = days
    history = list(data.get("mdi_history") or [])
    history.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "mdi": mdi})
    data["mdi_history"] = history[-90:]
    save_state(runtime_dir, data)


def gmcs_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    day = dict((data.get("days") or {}).get(day_key) or {})
    mdis = [float(x) for x in (day.get("mdi_scores") or [])]
    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "avg_mdi_today": round(sum(mdis) / len(mdis), 2) if mdis else 0.0,
        "vertical_wins_today": dict(day.get("vertical_wins") or {}),
        "objective": "telegram_ecosystem_competitive_substitution",
    }
