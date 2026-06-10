"""Runtime snapshot for editorial intelligence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.growth_layer.editorial.editorial_recommendations import generate_editorial_recommendations


def build_editorial_intelligence_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recs = generate_editorial_recommendations(rows)
    segments: dict[str, Any] = {}
    for segment, data in recs.items():
        if segment == "all":
            continue
        segments[segment] = {
            "winning_patterns": data.get("winning_patterns") or [],
            "anti_patterns": data.get("anti_patterns") or [],
        }
    return {
        "generated_from_posts": len(rows),
        "segments": segments,
        "global": {
            "winning_patterns": recs.get("all", {}).get("winning_patterns") or [],
            "anti_patterns": recs.get("all", {}).get("anti_patterns") or [],
        },
        "recommendations": recs,
    }


def persist_editorial_intelligence_snapshot(runtime_dir: str | Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = build_editorial_intelligence_snapshot(rows)
    path = Path(runtime_dir) / "editorial_intelligence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def load_editorial_intelligence_snapshot(runtime_dir: str | Path) -> dict[str, Any]:
    path = Path(runtime_dir) / "editorial_intelligence.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}
