"""Explainable source reputation (extends utils/source_reputation counters)."""

from __future__ import annotations

import time
from typing import Any

from editorial.governance.paths import governance_state_path
from editorial.intelligence_store import load_json, save_json
from utils.source_reputation import export_channel_scores_for_priority

from app.editorial.curated_sources import CURATED_SOURCE_CREDIBILITY, is_curated_source

def explainable_reputation(runtime_dir: str | None) -> dict[str, dict[str, Any]]:
    """Channel -> explainable reputation row for ranking and governance API."""
    base = export_channel_scores_for_priority(runtime_dir)
    state = load_json(governance_state_path(runtime_dir), {"version": 1, "ema_scores": {}})
    ema = dict(state.get("ema_scores") or {})
    out: dict[str, dict[str, Any]] = {}
    for ch, row in base.items():
        publishes = int(row.get("publishes") or 0)
        rejects = int(row.get("rejects") or 0)
        dups = int(row.get("duplicate_signals") or 0)
        total = max(1, publishes + rejects)
        dup_rate = round(dups / max(1, publishes + dups), 4)
        stale = int(row.get("stale_signals") or 0)
        stale_rate = round(stale / max(1, publishes), 4)
        score = float(row.get("score") or 0.5)
        prev = float(ema.get(ch) or score)
        # Slow EMA — reputation changes gradually
        blended = round(0.85 * prev + 0.15 * score, 4)
        if is_curated_source(ch):
            blended = CURATED_SOURCE_CREDIBILITY
        elif publishes < 3:
            blended = round(max(0.55 * 0.85, blended), 4)
        ema[ch] = blended
        out[ch] = {
            "score": blended,
            "raw_score": score,
            "publishes": publishes,
            "rejects": rejects,
            "duplicate_signals": dups,
            "duplicate_rate": dup_rate,
            "stale_signals": stale,
            "stale_rate": stale_rate,
            "approval_rate": row.get("approval_rate"),
            "reliability_label": _label(blended, dup_rate),
        }
    state["ema_scores"] = ema
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(governance_state_path(runtime_dir), state)
    return out


def _label(score: float, dup_rate: float) -> str:
    if score >= 0.75 and dup_rate < 0.25:
        return "high"
    if score >= 0.5 and dup_rate < 0.45:
        return "medium"
    return "low"


def record_stale_signal(channels: list[str], *, runtime_dir: str | None = None) -> None:
    from utils.source_reputation import record_stale_for_channels

    record_stale_for_channels(channels, runtime_dir=runtime_dir)


def reputation_snapshot(runtime_dir: str | None) -> dict[str, Any]:
    rows = explainable_reputation(runtime_dir)
    return {
        "channels": rows,
        "channel_count": len(rows),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
