"""Ad inventory optimization — slot timing and load balancing."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AdSlotDecision:
    allocate: bool
    slot_index: int
    predicted_ctr: float
    reason: str


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "ad_inventory_state.json"


def _max_daily() -> int:
    try:
        return max(0, min(6, int(os.getenv("W5_SPONSOR_MAX_DAILY", "2"))))
    except ValueError:
        return 2


def _load_state(runtime_dir: str) -> dict:
    try:
        return json.loads(_state_path(runtime_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(runtime_dir: str, state: dict) -> None:
    p = _state_path(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")


def predict_ctr_rule_based(
    *,
    topic_bucket: str,
    narrative_phase: str = "developing",
    hour_local: int = 12,
    audience_mood: float = 0.5,
) -> float:
    """Rule-based CTR proxy — no ML required for W5 v1."""
    base = 0.018
    if topic_bucket.split("_")[0] in ("crypto", "macro", "finance"):
        base += 0.006
    if narrative_phase in ("peak", "breaking"):
        base += 0.004
    if 8 <= hour_local <= 11 or 17 <= hour_local <= 20:
        base += 0.005
    base += (audience_mood - 0.5) * 0.01
    return round(min(0.08, max(0.005, base)), 4)


def allocate_ad_slot(
    *,
    runtime_dir: str,
    topic_bucket: str,
    narrative_phase: str = "developing",
    newsroom_tz: str = "Europe/Moscow",
    audience_mood: float = 0.5,
) -> AdSlotDecision:
    if os.getenv("W5_AD_INVENTORY_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return AdSlotDecision(False, 0, 0.0, "disabled")

    try:
        from datetime import datetime

        hour = datetime.now(ZoneInfo(newsroom_tz)).hour
        day = datetime.now(ZoneInfo(newsroom_tz)).strftime("%Y-%m-%d")
    except Exception:
        hour = 12
        day = time.strftime("%Y-%m-%d")

    state = _load_state(runtime_dir)
    day_state = dict(state.get(day) or {"used": 0, "slots": []})
    used = int(day_state.get("used") or 0)
    max_daily = _max_daily()

    if used >= max_daily:
        return AdSlotDecision(False, used, 0.0, "daily_cap")

    ctr = predict_ctr_rule_based(
        topic_bucket=topic_bucket,
        narrative_phase=narrative_phase,
        hour_local=hour,
        audience_mood=audience_mood,
    )
    min_ctr = float(os.getenv("W5_AD_MIN_PREDICTED_CTR", "0.015"))
    if ctr < min_ctr:
        return AdSlotDecision(False, used, ctr, "low_ctr")

    day_state["used"] = used + 1
    day_state["slots"] = list(day_state.get("slots") or []) + [{"ts": time.time(), "ctr": ctr}]
    state[day] = day_state
    keys = sorted(state.keys())
    for k in keys[:-14]:
        state.pop(k, None)
    _save_state(runtime_dir, state)

    return AdSlotDecision(True, used + 1, ctr, "ok")
