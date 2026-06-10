"""Portfolio-level aggregation by content segment."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.growth_layer.validation.acquisition_proxy import acquisition_proxy_score
from app.growth_layer.validation.status import filter_final_rows


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _round_pct(share: float) -> float:
    return round(share, 1)


def build_portfolio_analysis(
    rows: list[dict[str, Any]],
    *,
    final_only: bool = True,
) -> dict[str, Any]:
    """
    Aggregate editorial portfolio metrics per content_segment.
    Explainable ratios vs global baseline — no ML.
    """
    pool = filter_final_rows(rows) if final_only else list(rows)
    if not pool:
        return {"segments": {}, "global": {}, "total_posts": 0}

    by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        seg = str(row.get("content_segment") or "general_news")
        by_segment[seg].append(row)

    total_posts = len(pool)
    global_acq_vals = [acquisition_proxy_score(r) for r in pool]
    global_avg_acq = _mean(global_acq_vals) or 1.0
    global_avg_err = _mean([float(r["actual_err"]) for r in pool if r.get("actual_err") is not None])
    global_avg_fwd = _mean([float(r["actual_forwards"]) for r in pool if r.get("actual_forwards") is not None])
    total_acq = sum(global_acq_vals)

    segments: dict[str, Any] = {}
    for segment, seg_rows in sorted(by_segment.items()):
        n = len(seg_rows)
        acq_vals = [acquisition_proxy_score(r) for r in seg_rows]
        err_vals = [float(r["actual_err"]) for r in seg_rows if r.get("actual_err") is not None]
        fwd_vals = [float(r["actual_forwards"]) for r in seg_rows if r.get("actual_forwards") is not None]
        seg_acq_sum = sum(acq_vals)
        avg_acq = _mean(acq_vals) or 0.0
        roi_index = round(avg_acq / global_avg_acq, 2) if global_avg_acq > 1e-9 else 1.0

        segments[segment] = {
            "total_posts": n,
            "share_of_content": _round_pct(n / total_posts * 100.0),
            "acquisition_share": _round_pct(seg_acq_sum / total_acq * 100.0) if total_acq > 0 else 0.0,
            "avg_err": round(_mean(err_vals), 4) if _mean(err_vals) is not None else None,
            "avg_forwards": round(_mean(fwd_vals), 2) if _mean(fwd_vals) is not None else None,
            "acquisition_proxy_score": round(avg_acq, 4),
            "roi_index": roi_index,
        }

    return {
        "segments": segments,
        "total_posts": total_posts,
        "global": {
            "avg_err": round(global_avg_err, 4) if global_avg_err is not None else None,
            "avg_forwards": round(global_avg_fwd, 2) if global_avg_fwd is not None else None,
            "acquisition_proxy_score": round(global_avg_acq, 4),
            "total_acquisition": round(total_acq, 4),
        },
    }
