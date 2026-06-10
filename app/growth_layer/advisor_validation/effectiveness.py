"""Recommendation effectiveness metrics from outcome rows."""

from __future__ import annotations

from typing import Any

from app.growth_layer.statistics.effect_size import calculate_effect_size
from app.growth_layer.statistics.significance import compare_two_samples

_ALPHA = 0.05


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _lift_pct(adopted_avg: float | None, ignored_avg: float | None) -> float | None:
    if adopted_avg is None or ignored_avg is None or ignored_avg <= 1e-12:
        return None
    return round((adopted_avg - ignored_avg) / ignored_avg * 100.0, 1)


def _effectiveness_score(
    *,
    err_lift: float | None,
    forward_lift: float | None,
    adoption_rate: float,
    p_value: float | None,
    times_shown: int,
) -> int:
    if times_shown < 5:
        return 0
    score = 40.0
    if err_lift is not None:
        score += min(30.0, max(-10.0, err_lift / 2.0))
    if forward_lift is not None:
        score += min(15.0, max(-5.0, forward_lift / 3.0))
    score += min(15.0, adoption_rate / 4.0)
    if p_value is not None and p_value < _ALPHA:
        score += 15.0
    elif p_value is not None and p_value < 0.1:
        score += 5.0
    return max(0, min(100, int(round(score))))


def evaluate_recommendation_effectiveness(
    outcome_rows: list[dict[str, Any]],
    *,
    alpha: float = _ALPHA,
) -> dict[str, Any]:
    """
    Per recommendation_type aggregates: adoption rate, ERR/forwards lift, p-value.
    outcome_rows: flat rows from advisor_recommendation_outcomes with actuals populated.
    """
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in outcome_rows:
        if row.get("actual_err") is None:
            continue
        rtype = str(row.get("recommendation_type") or row.get("recommendation") or "")
        if not rtype:
            continue
        by_type.setdefault(rtype, []).append(row)

    results: dict[str, Any] = {}
    for rtype, rows in sorted(by_type.items()):
        times_shown = len(rows)
        adopted_rows = [r for r in rows if bool(r.get("adopted"))]
        ignored_rows = [r for r in rows if not bool(r.get("adopted"))]
        times_adopted = len(adopted_rows)
        adoption_rate = round(times_adopted / times_shown * 100.0, 1) if times_shown else 0.0

        adopted_err = [float(r["actual_err"]) for r in adopted_rows if r.get("actual_err") is not None]
        ignored_err = [float(r["actual_err"]) for r in ignored_rows if r.get("actual_err") is not None]
        adopted_fwd = [float(r["actual_forwards"]) for r in adopted_rows if r.get("actual_forwards") is not None]
        ignored_fwd = [float(r["actual_forwards"]) for r in ignored_rows if r.get("actual_forwards") is not None]

        err_lift = _lift_pct(_avg(adopted_err), _avg(ignored_err))
        forward_lift = _lift_pct(_avg(adopted_fwd), _avg(ignored_fwd))

        sig = compare_two_samples(adopted_err, ignored_err, alternative="greater") if adopted_err and ignored_err else {}
        p_value = sig.get("p_value")
        effect = calculate_effect_size(adopted_err, ignored_err)

        results[rtype] = {
            "recommendation": rtype,
            "times_shown": times_shown,
            "times_adopted": times_adopted,
            "adoption_rate": adoption_rate,
            "err_lift": err_lift,
            "forward_lift": forward_lift,
            "adopted_err_avg": round(_avg(adopted_err), 4) if _avg(adopted_err) is not None else None,
            "ignored_err_avg": round(_avg(ignored_err), 4) if _avg(ignored_err) is not None else None,
            "p_value": p_value,
            "effect_size": effect.get("value"),
            "effect_size_class": effect.get("classification"),
            "statistically_significant": p_value is not None and float(p_value) < alpha,
            "confidence_interval": {
                "metric": "actual_err",
                "adopted": compare_two_samples(adopted_err, adopted_err).get("p_value"),
            },
            "effectiveness_score": _effectiveness_score(
                err_lift=err_lift,
                forward_lift=forward_lift,
                adoption_rate=adoption_rate,
                p_value=float(p_value) if p_value is not None else None,
                times_shown=times_shown,
            ),
        }
    return results
