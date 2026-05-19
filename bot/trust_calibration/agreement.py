from __future__ import annotations

from collections import defaultdict
from typing import Any


def _warnings_from_trace(trace: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    eq = trace.get("editorial_quality") or {}
    if isinstance(eq, dict):
        for w in eq.get("warnings") or []:
            out["editorial_quality"].append(str(w))
    em = trace.get("editorial_memory") or {}
    if isinstance(em, dict):
        for w in em.get("warnings") or []:
            out["memory_matching"].append(str(w))
            out["contradiction_detection"].append(str(w))
    ep = trace.get("editorial_priority") or {}
    if isinstance(ep, dict):
        for w in ep.get("warnings") or []:
            out["prioritization"].append(str(w))
    for w in eq.get("warnings") or []:
        if "fatigue" in str(w).lower() or "saturation" in str(w).lower():
            out["fatigue_detection"].append(str(w))
    return out


def analyze_operator_agreement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compare operator good/bad ratings with subsystem signals at publish time.
    """
    totals = {
        "rated": 0,
        "good": 0,
        "bad": 0,
        "priority_high_agree": 0,
        "priority_high_disagree": 0,
        "warning_confirmed": 0,
        "warning_false_positive": 0,
        "warning_ignored_then_bad": 0,
    }
    by_subsystem: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "agreement": 0,
            "disagreement": 0,
        },
    )

    for row in rows:
        rating = str(row.get("rating") or "").lower()
        if rating not in ("good", "bad"):
            continue
        totals["rated"] += 1
        totals["good" if rating == "good" else "bad"] += 1
        trace = row.get("trace") or {}
        is_bad = rating == "bad"

        pri_score = float(trace.get("editorial_priority_score") or 0)
        if pri_score >= 0.68:
            if is_bad:
                totals["priority_high_disagree"] += 1
                by_subsystem["prioritization"]["disagreement"] += 1
            else:
                totals["priority_high_agree"] += 1
                by_subsystem["prioritization"]["agreement"] += 1

        warnings = _warnings_from_trace(trace)
        for subsystem, warns in warnings.items():
            if not warns:
                continue
            if is_bad:
                totals["warning_confirmed"] += 1
                by_subsystem[subsystem]["true_positive"] += 1
            else:
                totals["warning_false_positive"] += 1
                by_subsystem[subsystem]["false_positive"] += 1

        if is_bad and not any(warnings.values()):
            totals["warning_ignored_then_bad"] += 1
            for sub in ("editorial_quality", "prioritization", "memory_matching"):
                by_subsystem[sub]["false_negative"] += 1

    return {"totals": totals, "by_subsystem": dict(by_subsystem)}
