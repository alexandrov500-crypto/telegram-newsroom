"""Segment routing API (preparation only — no auto-routing in Phase 2B)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.growth_layer.segments.content_segments import ContentSegment
from app.growth_layer.segments.segment_decision import build_segment_decision_map, evaluate_segment_strategy


def _default_mode() -> str:
    return "hybrid"


def load_segment_decisions_snapshot(runtime_dir: str | Path) -> dict[str, Any]:
    path = Path(runtime_dir) / "growth_segment_decisions.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_recommended_mode_for_segment(
    segment: str,
    *,
    runtime_dir: str | Path | None = None,
    snapshot: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Prepared API for future segment-adaptive routing.
    Does NOT change publish routing — read-only recommendation.
    """
    normalized = str(segment or ContentSegment.GENERAL_NEWS.value).strip().lower()
    if rows is not None:
        verdict = evaluate_segment_strategy(normalized, rows)
        return {
            "segment": normalized,
            "recommended_mode": verdict["recommended_mode"],
            "confidence": verdict["confidence"],
            "statistically_significant": verdict["statistically_significant"],
            "routing_readiness_score": verdict["routing_readiness_score"],
            "source": "live_rows",
        }

    data = snapshot if snapshot is not None else (
        load_segment_decisions_snapshot(runtime_dir) if runtime_dir is not None else {}
    )
    segments = data.get("segments") if isinstance(data, dict) else {}
    entry = segments.get(normalized) if isinstance(segments, dict) else None
    if isinstance(entry, dict):
        return {
            "segment": normalized,
            "recommended_mode": str(entry.get("recommended_mode") or _default_mode()),
            "confidence": str(entry.get("confidence") or "LOW"),
            "statistically_significant": bool(entry.get("statistically_significant")),
            "routing_readiness_score": int(entry.get("routing_readiness_score") or 0),
            "source": "snapshot",
        }
    return {
        "segment": normalized,
        "recommended_mode": _default_mode(),
        "confidence": "LOW",
        "statistically_significant": False,
        "routing_readiness_score": 0,
        "source": "default",
    }


def persist_segment_decisions_snapshot(runtime_dir: str | Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = build_segment_decision_map(rows)
    path = Path(runtime_dir) / "growth_segment_decisions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot
