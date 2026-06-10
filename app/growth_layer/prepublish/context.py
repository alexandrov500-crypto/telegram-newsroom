"""Load segment discovery context for pre-publication advisor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.growth_layer.editorial.enriched_rows import load_enriched_validation_rows
from app.growth_layer.editorial.pattern_discovery import discover_growth_patterns
from app.growth_layer.editorial.snapshot import load_editorial_intelligence_snapshot


def discovery_from_snapshot(snapshot: dict[str, Any], segment: str) -> dict[str, Any] | None:
    recs = snapshot.get("recommendations") if isinstance(snapshot.get("recommendations"), dict) else {}
    seg_data = recs.get(segment) or recs.get("all") or {}
    discovery = seg_data.get("discovery")
    if isinstance(discovery, dict) and discovery.get("patterns"):
        return discovery
    return None


def load_segment_discovery(
    segment: str,
    *,
    runtime_dir: str | Path | None = None,
    snapshot: dict[str, Any] | None = None,
    historical_rows: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str, int]:
    """
    Return (discovery, data_source, sample_size).
    Prefers editorial_intelligence.json snapshot; falls back to live discovery from rows.
    """
    normalized = str(segment or "general_news").strip().lower()
    data = snapshot if snapshot is not None else (
        load_editorial_intelligence_snapshot(runtime_dir) if runtime_dir is not None else {}
    )
    found = discovery_from_snapshot(data, normalized)
    if found is not None:
        return found, "editorial_intelligence.json", int(found.get("sample_size") or 0)

    if historical_rows:
        pool = [r for r in historical_rows if str(r.get("content_segment") or "") == normalized]
        if len(pool) >= 5:
            discovery = discover_growth_patterns(historical_rows, segment=normalized)
            if discovery.get("patterns"):
                return discovery, "live_discovery", int(discovery.get("sample_size") or 0)
        discovery = discover_growth_patterns(historical_rows, segment=None)
        if discovery.get("patterns"):
            return discovery, "live_discovery_global", int(discovery.get("sample_size") or 0)

    return {
        "segment": normalized,
        "metric": "err",
        "sample_size": 0,
        "patterns": {},
        "numeric_patterns": {},
    }, "insufficient_data", 0


async def load_historical_rows(session: Any, *, limit: int = 500) -> list[dict[str, Any]]:
    return await load_enriched_validation_rows(session, limit=limit)
