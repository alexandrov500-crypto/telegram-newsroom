"""Per-segment performance statistics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.growth_layer.statistics.decision_metrics import compare_content_formats
from app.growth_layer.validation.status import filter_final_rows


def _mean_forwards(rows: list[dict[str, Any]]) -> float | None:
    vals = [float(r["actual_forwards"]) for r in rows if r.get("actual_forwards") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def _segment_performance_block(
    segment: str,
    growth_rows: list[dict[str, Any]],
    cb_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    cmp = compare_content_formats(growth_rows, cb_rows)
    err_es = cmp.get("err_effect_size") or {}
    return {
        "segment": segment,
        "growth_posts": len(growth_rows),
        "cb_posts": len(cb_rows),
        "growth_err": cmp.get("growth_mean_err"),
        "cb_err": cmp.get("cb_mean_err"),
        "growth_forwards": _mean_forwards(growth_rows),
        "cb_forwards": _mean_forwards(cb_rows),
        "growth_forward_rate": cmp.get("growth_mean_forwards"),
        "cb_forward_rate": cmp.get("cb_mean_forwards"),
        "err_lift_pct": cmp.get("err_lift_pct"),
        "forward_lift_pct": cmp.get("forward_lift_pct"),
        "err_p_value": cmp.get("err_p_value"),
        "forward_p_value": cmp.get("forward_p_value"),
        "p_value": cmp.get("err_p_value"),
        "effect_size": str(err_es.get("classification") or "unknown"),
        "err_effect_size": err_es,
        "forward_effect_size": cmp.get("forward_effect_size") or {},
        "comparison": cmp,
    }


def build_segment_performance(
    rows: list[dict[str, Any]],
    *,
    final_only: bool = True,
) -> list[dict[str, Any]]:
    """Aggregate FINAL validation rows by content_segment."""
    pool = filter_final_rows(rows) if final_only else list(rows)
    by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        seg = str(row.get("content_segment") or "general_news")
        by_segment[seg].append(row)

    results: list[dict[str, Any]] = []
    for segment in sorted(by_segment.keys()):
        seg_rows = by_segment[segment]
        growth_rows = [r for r in seg_rows if str(r.get("format_profile") or "") == "growth_brief"]
        cb_rows = [r for r in seg_rows if str(r.get("format_profile") or "") == "cb_brief"]
        if not growth_rows and not cb_rows:
            continue
        results.append(_segment_performance_block(segment, growth_rows, cb_rows))
    return results
