"""Observable UEOS state — decisions, conflicts, compression events."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "ueos_state.json"


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


def record_ueos_decision(
    runtime_dir: str | None,
    *,
    ueos_total: float,
    action: str,
    conflicts: list[str] | None = None,
    compression: bool = False,
    replacement_score: int = 0,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    scores = list(day.get("ueos_scores") or [])
    scores.append(float(ueos_total))
    day["ueos_scores"] = scores[-300:]

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1

    actions = dict(day.get("action_counts") or {})
    actions[action] = int(actions.get(action) or 0) + 1
    day["action_counts"] = actions

    if conflicts:
        conflict_log = list(day.get("conflicts") or [])
        conflict_log.extend(conflicts[-5:])
        day["conflicts"] = conflict_log[-100:]

    if compression:
        day["compression_events"] = int(day.get("compression_events") or 0) + 1

    rep_scores = list(day.get("replacement_scores") or [])
    rep_scores.append(int(replacement_score))
    day["replacement_scores"] = rep_scores[-300:]

    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def ueos_state_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    scores = [float(x) for x in (day.get("ueos_scores") or [])]
    rep = [int(x) for x in (day.get("replacement_scores") or [])]

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "ueos_avg": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "pct_flagship_gte_88": round(sum(1 for s in scores if s >= 88) / max(1, len(scores)) * 100, 1),
        "action_counts": dict(day.get("action_counts") or {}),
        "compression_events_today": int(day.get("compression_events") or 0),
        "conflicts_logged": len(day.get("conflicts") or []),
        "avg_channels_replaced": round(sum(rep) / len(rep), 2) if rep else 0.0,
        "core_kpi": "single_channel_substitution_rate",
        "objective": "maximize_cognitive_replacement_of_external_information_ecosystem",
    }
