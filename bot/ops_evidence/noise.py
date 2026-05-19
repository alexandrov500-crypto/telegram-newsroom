from __future__ import annotations

from typing import Any

from bot.ops_evidence.types import RetirementLabel


def detect_retirement_candidates(
    signal_rankings: list[dict[str, Any]],
    subsystems: dict[str, dict[str, Any]],
    noise_metrics: dict[str, int],
) -> list[dict[str, Any]]:
    """Advisory labels for noisy or low-value signals — never auto-applied."""
    candidates: list[dict[str, Any]] = []

    for row in signal_rankings:
        precision = float(row.get("precision") or 0)
        ignore_ratio = float(row.get("ignore_ratio") or 0)
        emitted = int(row.get("emitted") or 0)
        if emitted < 3:
            continue

        label: RetirementLabel | None = None
        reason = ""
        if ignore_ratio >= 0.7 and precision < 0.35:
            label = RetirementLabel.CANDIDATE_FOR_REMOVAL
            reason = "frequently ignored with poor precision"
        elif ignore_ratio >= 0.55 or (precision < 0.4 and emitted >= 5):
            label = RetirementLabel.CANDIDATE_FOR_SUPPRESSION
            reason = "high ignore rate or low precision"
        elif precision < 0.5 and ignore_ratio >= 0.35:
            label = RetirementLabel.CANDIDATE_FOR_TUNING
            reason = "moderate noise — consider threshold adjustment"

        if label:
            candidates.append(
                {
                    "signal": row["signal"],
                    "subsystem": row["subsystem"],
                    "label": label.value,
                    "reason": reason,
                    "precision": precision,
                    "ignore_ratio": ignore_ratio,
                    "emitted": emitted,
                },
            )

    for sub, metrics in subsystems.items():
        ignored = float(metrics.get("ignored_ratio") or 0)
        prec = float(metrics.get("precision") or 0.5)
        if ignored >= 0.6 and prec < 0.4:
            candidates.append(
                {
                    "signal": f"{sub}:*",
                    "subsystem": sub,
                    "label": RetirementLabel.CANDIDATE_FOR_TUNING.value,
                    "reason": "subsystem-wide ignore pattern",
                    "precision": prec,
                    "ignore_ratio": ignored,
                    "emitted": int(metrics.get("event_count") or 0),
                },
            )

    suppressed = int(noise_metrics.get("suppressed") or 0)
    delivered = int(noise_metrics.get("delivered") or 0)
    if delivered and suppressed / max(1, delivered + suppressed) > 0.65:
        candidates.append(
            {
                "signal": "attention:delivery",
                "subsystem": "operator_ux",
                "label": RetirementLabel.CANDIDATE_FOR_SUPPRESSION.value,
                "reason": "attention alerts mostly suppressed — review bundling thresholds",
                "precision": 0.0,
                "ignore_ratio": round(suppressed / max(1, delivered + suppressed), 3),
                "emitted": delivered + suppressed,
            },
        )

    return candidates[:25]
