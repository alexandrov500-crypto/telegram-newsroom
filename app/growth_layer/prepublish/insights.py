"""Aggregate pre-publication advisor outcomes vs post-publish performance."""

from __future__ import annotations

from typing import Any


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def build_prepublication_insights(
    advice_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Join draft_growth_advice with FINAL validation rows by draft_id.
    Returns aggregate stats for weekly report.
    """
    by_draft = {int(r["draft_id"]): r for r in validation_rows if r.get("draft_id") is not None}
    joined: list[dict[str, Any]] = []
    for advice in advice_rows:
        draft_id = int(advice.get("draft_id") or 0)
        val = by_draft.get(draft_id)
        if val is None or val.get("actual_err") is None:
            continue
        joined.append(
            {
                "draft_id": draft_id,
                "alignment_score": int(advice.get("alignment_score") or 0),
                "actual_err": float(val.get("actual_err") or 0),
                "actual_forwards": float(val.get("actual_forwards") or 0),
                "segment": str(advice.get("predicted_segment") or val.get("content_segment") or ""),
            }
        )

    if not joined:
        return {
            "sample_size": 0,
            "average_alignment_score": None,
            "strong_err_avg": None,
            "weak_err_avg": None,
            "strong_lift_pct": None,
            "weak_lift_pct": None,
        }

    scores = [j["alignment_score"] for j in joined]
    overall_err = _avg([j["actual_err"] for j in joined]) or 0.0
    strong = [j for j in joined if j["alignment_score"] >= 85]
    weak = [j for j in joined if j["alignment_score"] < 60]
    strong_err = _avg([j["actual_err"] for j in strong])
    weak_err = _avg([j["actual_err"] for j in weak])

    strong_lift = None
    if strong_err is not None and overall_err > 0:
        strong_lift = round((strong_err - overall_err) / overall_err * 100.0, 1)
    weak_lift = None
    if weak_err is not None and overall_err > 0:
        weak_lift = round((weak_err - overall_err) / overall_err * 100.0, 1)

    return {
        "sample_size": len(joined),
        "average_alignment_score": round(sum(scores) / len(scores), 1),
        "strong_count": len(strong),
        "weak_count": len(weak),
        "strong_err_avg": round(strong_err, 4) if strong_err is not None else None,
        "weak_err_avg": round(weak_err, 4) if weak_err is not None else None,
        "strong_lift_pct": strong_lift,
        "weak_lift_pct": weak_lift,
    }
