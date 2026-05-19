from __future__ import annotations

from collections import defaultdict
from typing import Any

from bot.trust_calibration.types import SUBSYSTEMS, TrustBand, band_for_scores


def compute_subsystem_metrics(
    events: list[dict[str, Any]],
    agreement: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Rolling reliability, precision, stability per subsystem."""
    by_sub: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        by_sub[str(ev.get("subsystem") or "unknown")].append(ev)

    agree_sub = agreement.get("by_subsystem") or {}
    metrics: dict[str, dict[str, Any]] = {}

    for subsystem in SUBSYSTEMS:
        evs = by_sub.get(subsystem, [])
        ag = agree_sub.get(subsystem, {})
        tp = int(ag.get("true_positive") or 0)
        fp = int(ag.get("false_positive") or 0)
        fn = int(ag.get("false_negative") or 0)
        agree = int(ag.get("agreement") or 0)
        disagree = int(ag.get("disagreement") or 0)

        precision = tp / (tp + fp) if (tp + fp) else 0.5
        recall = tp / (tp + fn) if (tp + fn) else 0.5
        reliability = (agree + tp) / max(1, agree + disagree + tp + fp + fn)
        ignored = sum(1 for e in evs if e.get("operator_action") == "ignored")

        scores: list[float] = []
        for e in evs:
            try:
                scores.append(float(e.get("signal_value") or 0))
            except (TypeError, ValueError):
                pass
        stability = 1.0
        if len(scores) >= 3:
            mean = sum(scores) / len(scores)
            var = sum((s - mean) ** 2 for s in scores) / len(scores)
            stability = max(0.0, 1.0 - min(1.0, var * 4))

        band = band_for_scores(
            reliability=reliability,
            precision=precision,
            stability=stability,
        )
        metrics[subsystem] = {
            "reliability": round(reliability, 3),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "stability": round(stability, 3),
            "ignored_ratio": round(ignored / max(1, len(evs)), 3),
            "event_count": len(evs),
            "trust_band": band.value,
        }
    return metrics


def detect_reliability_decay(
    current: dict[str, dict[str, Any]],
    historical: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag subsystems whose precision dropped vs prior week."""
    alerts: list[dict[str, Any]] = []
    if not historical:
        return alerts

    by_sub: dict[str, list[float]] = defaultdict(list)
    for row in historical:
        sub = row.get("subsystem")
        prec = (row.get("metrics") or {}).get("precision")
        if sub and prec is not None:
            by_sub[str(sub)].append(float(prec))

    for sub, cur in current.items():
        hist = by_sub.get(sub, [])
        if len(hist) < 2:
            continue
        prior = sum(hist[len(hist) // 2 :]) / max(1, len(hist) - len(hist) // 2)
        now = float(cur.get("precision") or 0)
        if prior - now >= 0.2 and now < 0.45:
            alerts.append(
                {
                    "subsystem": sub,
                    "severity": "important",
                    "message": f"{sub} precision fell {prior - now:.2f} — review before relying on signals",
                },
            )
    return alerts
