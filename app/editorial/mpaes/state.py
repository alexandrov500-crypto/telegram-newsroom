"""MPAES persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "mpaes_state.json"


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


def record_mpaes_evaluation(
    runtime_dir: str | None,
    *,
    dual_audience_trust: float,
    hub_substitution_score: float,
    vertical: str,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    trusts = list(day.get("dual_trusts") or [])
    trusts.append(float(dual_audience_trust))
    day["dual_trusts"] = trusts[-200:]

    subs = list(day.get("substitution_scores") or [])
    subs.append(float(hub_substitution_score))
    day["substitution_scores"] = subs[-200:]

    verts = dict(day.get("vertical_counts") or {})
    verts[vertical] = int(verts.get(vertical) or 0) + 1
    day["vertical_counts"] = verts

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1

    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def mpaes_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    day = dict((data.get("days") or {}).get(day_key) or {})
    trusts = [float(x) for x in (day.get("dual_trusts") or [])]
    subs = [float(x) for x in (day.get("substitution_scores") or [])]

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "avg_dual_trust": round(sum(trusts) / len(trusts), 3) if trusts else 0.0,
        "avg_substitution_score": round(sum(subs) / len(subs), 2) if subs else 0.0,
        "vertical_counts_today": dict(day.get("vertical_counts") or {}),
        "objective": "multi_persona_hub_substitution",
    }
