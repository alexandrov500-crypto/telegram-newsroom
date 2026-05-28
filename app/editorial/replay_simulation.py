"""Offline replay of desk decisions on recent rejections (tuning validation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.desk_starvation import desk_threshold_context
from app.editorial.scoring_engine import score_story
from ops.pipeline.paths import runtime_root


def replay_rejected_items(
    runtime_dir: str | None,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    path = runtime_root(runtime_dir) / "rejected_items.jsonl"
    if not path.is_file():
        return {"count": 0, "path": str(path), "results": []}
    ctx = desk_threshold_context()
    results: list[dict[str, Any]] = []
    would_publish = 0
    would_reject = 0
    for line in path.read_text(encoding="utf-8").splitlines()[:limit]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = str(row.get("text_preview") or "")
        sources = list(row.get("sources") or [])
        escore = score_story(text=text, sources=sources, runtime_dir=runtime_dir)
        desk = evaluate_desk_filter(text, escore, sources=sources, runtime_dir=runtime_dir)
        prev = (row.get("desk") or {}).get("publish")
        if desk.publish:
            would_publish += 1
        else:
            would_reject += 1
        results.append(
            {
                "article_id": row.get("article_id"),
                "was_publish": prev,
                "now_publish": desk.publish,
                "was_reason": (row.get("desk") or {}).get("reason"),
                "now_reason": desk.reason,
                "now_reason_code": desk.reason_code,
                "quality": desk.quality_score,
                "threshold": desk.threshold_used,
            }
        )
    return {
        "count": len(results),
        "path": str(path),
        "threshold_ctx": {
            "effective_min": ctx.effective_min_publish_score,
            "starvation": ctx.publish_starvation_detected,
        },
        "would_publish": would_publish,
        "would_reject": would_reject,
        "flip_to_publish": sum(1 for r in results if not r["was_publish"] and r["now_publish"]),
        "flip_to_reject": sum(1 for r in results if r["was_publish"] and not r["now_publish"]),
        "results": results[:20],
    }
