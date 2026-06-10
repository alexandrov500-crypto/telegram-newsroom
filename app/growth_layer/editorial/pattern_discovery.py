"""Discover explainable patterns in top vs bottom performing posts."""

from __future__ import annotations

from typing import Any

BOOLEAN_FEATURES = (
    "has_number",
    "has_percent",
    "has_currency",
    "has_question",
    "has_colon",
    "has_quote",
)

NUMERIC_FEATURES = (
    "headline_length",
    "headline_word_count",
    "body_length",
    "paragraph_count",
    "bullet_count",
    "emoji_count",
    "link_count",
    "source_count",
    "uppercase_ratio",
)

METRIC_KEYS = {
    "err": "actual_err",
    "forwards": "actual_forwards",
    "engagement": "actual_engagement",
    "acquisition_score": "acquisition_proxy_score",
}


def _metric_value(row: dict[str, Any], metric: str) -> float:
    key = METRIC_KEYS.get(metric, metric)
    val = row.get(key)
    if val is None and metric == "acquisition_score":
        from app.growth_layer.validation.acquisition_proxy import acquisition_proxy_score

        return float(acquisition_proxy_score(row))
    return float(val or 0.0)


def _quantile_split(rows: list[dict[str, Any]], metric: str = "err") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 5:
        return [], []
    ranked = sorted(rows, key=lambda r: _metric_value(r, metric), reverse=True)
    n = len(ranked)
    k = max(1, int(round(n * 0.2)))
    return ranked[:k], ranked[-k:]


def _bool_rate(rows: list[dict[str, Any]], feature: str) -> float:
    if not rows:
        return 0.0
    hits = sum(1 for r in rows if bool(r.get(feature)))
    return round(hits / len(rows), 4)


def _num_mean(rows: list[dict[str, Any]], feature: str) -> float:
    vals = [float(r[feature]) for r in rows if r.get(feature) is not None]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)


def _lift_pct(top: float, bottom: float) -> float | None:
    if bottom <= 1e-9:
        return round(top * 100.0, 1) if top > 0 else None
    return round((top - bottom) / bottom * 100.0, 1)


def _numeric_range(rows: list[dict[str, Any]], feature: str) -> dict[str, float | None]:
    vals = sorted(float(r[feature]) for r in rows if r.get(feature) is not None)
    if not vals:
        return {"low": None, "high": None, "median": None}
    mid = len(vals) // 2
    if len(vals) % 2:
        med = vals[mid]
    else:
        med = (vals[mid - 1] + vals[mid]) / 2.0
    q1 = vals[max(0, len(vals) // 4)]
    q3 = vals[min(len(vals) - 1, (3 * len(vals)) // 4)]
    return {"low": round(q1, 2), "high": round(q3, 2), "median": round(med, 2)}


def discover_growth_patterns(
    rows: list[dict[str, Any]],
    *,
    metric: str = "err",
    segment: str | None = None,
) -> dict[str, Any]:
    """
    Compare top 20% vs bottom 20% posts by metric.
    Rows must include editorial features + performance metrics.
    """
    pool = list(rows)
    if segment:
        pool = [r for r in pool if str(r.get("content_segment") or "") == segment]
    top, bottom = _quantile_split(pool, metric=metric)
    if not top or not bottom:
        return {
            "segment": segment or "all",
            "metric": metric,
            "sample_size": len(pool),
            "top_count": len(top),
            "bottom_count": len(bottom),
            "patterns": {},
            "numeric_patterns": {},
        }

    patterns: dict[str, Any] = {}
    for feat in BOOLEAN_FEATURES:
        top_rate = _bool_rate(top, feat)
        bottom_rate = _bool_rate(bottom, feat)
        patterns[feat] = {
            "top": top_rate,
            "bottom": bottom_rate,
            "lift": _lift_pct(top_rate, bottom_rate),
        }

    numeric_patterns: dict[str, Any] = {}
    for feat in NUMERIC_FEATURES:
        top_mean = _num_mean(top, feat)
        bottom_mean = _num_mean(bottom, feat)
        numeric_patterns[feat] = {
            "top_mean": top_mean,
            "bottom_mean": bottom_mean,
            "lift": _lift_pct(top_mean, bottom_mean),
            "top_range": _numeric_range(top, feat),
        }

    return {
        "segment": segment or "all",
        "metric": metric,
        "sample_size": len(pool),
        "top_count": len(top),
        "bottom_count": len(bottom),
        "patterns": patterns,
        "numeric_patterns": numeric_patterns,
    }


def discover_all_segment_patterns(rows: list[dict[str, Any]], *, metric: str = "err") -> dict[str, Any]:
    segments = sorted({str(r.get("content_segment") or "general_news") for r in rows})
    out: dict[str, Any] = {"all": discover_growth_patterns(rows, metric=metric)}
    for seg in segments:
        out[seg] = discover_growth_patterns(rows, metric=metric, segment=seg)
    return out
