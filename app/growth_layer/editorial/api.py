"""Editorial intelligence API (analysis-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.growth_layer.editorial.editorial_recommendations import generate_editorial_recommendations
from app.growth_layer.editorial.snapshot import load_editorial_intelligence_snapshot


def get_segment_editorial_recommendations(
    segment: str,
    *,
    runtime_dir: str | Path | None = None,
    snapshot: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return winning editorial pattern bullets for a segment."""
    normalized = str(segment or "general_news").strip().lower()
    if rows is not None:
        recs = generate_editorial_recommendations(rows)
        seg_data = recs.get(normalized) or recs.get("all") or {}
        return list(seg_data.get("winning_patterns") or [])

    data = snapshot if snapshot is not None else (
        load_editorial_intelligence_snapshot(runtime_dir) if runtime_dir is not None else {}
    )
    segments = data.get("segments") if isinstance(data, dict) else {}
    if isinstance(segments, dict):
        entry = segments.get(normalized) or {}
        if entry.get("winning_patterns"):
            return list(entry["winning_patterns"])
    global_block = data.get("global") if isinstance(data, dict) else {}
    if isinstance(global_block, dict):
        return list(global_block.get("winning_patterns") or [])
    return []
