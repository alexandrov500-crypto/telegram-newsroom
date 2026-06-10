"""PEOS observable state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "product_os_state.json"


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


def record_peos_evaluation(
    runtime_dir: str | None,
    *,
    pg_total: float,
    substitution_score: float,
    forward_prediction: float,
    cta_type: str,
    content_format: str,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    for key, val in (
        ("pg_scores", pg_total),
        ("substitution_scores", substitution_score),
        ("forward_predictions", forward_prediction),
    ):
        arr = list(day.get(key) or [])
        arr.append(float(val))
        day[key] = arr[-300:]

    fmt_counts = dict(day.get("format_counts") or {})
    fmt_counts[content_format] = int(fmt_counts.get(content_format) or 0) + 1
    day["format_counts"] = fmt_counts

    cta_counts = dict(day.get("cta_type_counts") or {})
    cta_counts[cta_type] = int(cta_counts.get(cta_type) or 0) + 1
    day["cta_type_counts"] = cta_counts

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1

    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def product_os_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})

    def _avg(key: str) -> float:
        vals = [float(x) for x in (day.get(key) or [])]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "pg_avg": _avg("pg_scores"),
        "substitution_avg": _avg("substitution_scores"),
        "forward_prediction_avg": _avg("forward_predictions"),
        "format_counts": dict(day.get("format_counts") or {}),
        "cta_type_counts": dict(day.get("cta_type_counts") or {}),
        "core_kpis": {
            "substitution_rate": "primary",
            "forwards_per_post": "track_via_telegram_analytics",
            "saves_per_post": "track_via_telegram_analytics",
            "return_visits_24h": "track_via_subscriber_cohorts",
            "multi_post_daily_read_ratio": "track_via_engagement_proxy",
            "digest_completion_rate": "track_via_engagement_proxy",
            "cross_domain_engagement_index": "derived_from_cse",
        },
        "objective": "maximize_cognitive_substitution_per_user_per_day",
    }
