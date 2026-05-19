from __future__ import annotations

from collections import defaultdict
from typing import Any


def rank_signal_effectiveness(
    events: list[dict[str, Any]],
    agreement: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Rank warnings/signals by usefulness (precision, operator confirmation, ignore rate).
    """
    by_signal: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "emitted": 0,
            "confirmed": 0,
            "false_positive": 0,
            "ignored": 0,
        },
    )

    for ev in events:
        st = str(ev.get("signal_type") or "unknown")
        sub = str(ev.get("subsystem") or "unknown")
        key = f"{sub}:{st}"
        by_signal[key]["emitted"] += 1
        action = str(ev.get("operator_action") or "")
        outcome = str(ev.get("outcome") or "")
        if outcome == "true_positive" or action == "confirmed":
            by_signal[key]["confirmed"] += 1
        elif outcome == "false_positive" or action == "ignored":
            by_signal[key]["false_positive"] += 1
            by_signal[key]["ignored"] += 1

    agree_sub = agreement.get("by_subsystem") or {}
    ranked: list[dict[str, Any]] = []

    for key, counts in by_signal.items():
        emitted = counts["emitted"]
        confirmed = counts["confirmed"]
        fp = counts["false_positive"]
        precision = confirmed / (confirmed + fp) if (confirmed + fp) else 0.5
        ignore_ratio = counts["ignored"] / max(1, emitted)
        usefulness = precision * (1.0 - min(0.9, ignore_ratio))
        sub = key.split(":", 1)[0]
        sub_ag = agree_sub.get(sub, {})
        ranked.append(
            {
                "signal": key,
                "subsystem": sub,
                "emitted": emitted,
                "confirmed": confirmed,
                "false_positive": fp,
                "precision": round(precision, 3),
                "ignore_ratio": round(ignore_ratio, 3),
                "usefulness_score": round(usefulness, 3),
                "subsystem_agreement": sub_ag,
            },
        )

    ranked.sort(key=lambda x: (-x["usefulness_score"], -x["emitted"]))
    return ranked
