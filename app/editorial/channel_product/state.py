"""Observable state for channel product growth loop."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "channel_product_state.json"


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


def record_channel_product_event(
    runtime_dir: str | None,
    *,
    loop_stage: str,
    viral_tier: str,
    cta_variant_id: str,
    reference_forward_score: float,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    loops = dict(day.get("loop_counts") or {})
    loops[loop_stage] = int(loops.get(loop_stage) or 0) + 1
    day["loop_counts"] = loops

    tiers = dict(day.get("viral_tier_counts") or {})
    tiers[viral_tier] = int(tiers.get(viral_tier) or 0) + 1
    day["viral_tier_counts"] = tiers

    ctas = dict(day.get("cta_variant_counts") or {})
    ctas[cta_variant_id] = int(ctas.get(cta_variant_id) or 0) + 1
    day["cta_variant_counts"] = ctas

    scores = list(day.get("reference_forward_scores") or [])
    scores.append(float(reference_forward_score))
    day["reference_forward_scores"] = scores[-300:]

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1

    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def channel_product_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    scores = [float(x) for x in (day.get("reference_forward_scores") or [])]

    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "loop_distribution": dict(day.get("loop_counts") or {}),
        "viral_tier_distribution": dict(day.get("viral_tier_counts") or {}),
        "avg_reference_forward_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "core_kpi": "single_channel_substitution_rate",
        "objective": "telegram_native_growth_loop",
    }
