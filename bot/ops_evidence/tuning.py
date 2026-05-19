from __future__ import annotations

from typing import Any

from bot.trust_calibration.types import TrustBand


def generate_tuning_suggestions(
    *,
    subsystems: dict[str, dict[str, Any]],
    signal_rankings: list[dict[str, Any]],
    retirement_candidates: list[dict[str, Any]],
    runtime: dict[str, Any],
    incident_patterns: list[dict[str, Any]],
) -> list[str]:
    """Advisory human-readable tuning suggestions — never auto-applied."""
    suggestions: list[str] = []

    for sub, m in subsystems.items():
        band = str(m.get("trust_band") or "")
        prec = float(m.get("precision") or 0)
        ignored = float(m.get("ignored_ratio") or 0)

        if band == TrustBand.HIGHLY_RELIABLE.value:
            suggestions.append(f"{sub} is highly reliable — suitable as a primary signal")
        elif ignored >= 0.55 and sub == "fatigue_detection":
            suggestions.append("fatigue detection appears overly sensitive — consider raising thresholds")
        elif ignored >= 0.5 and sub == "prioritization":
            suggestions.append("priority scoring may not align with operator judgment — review rank weights")
        elif prec >= 0.65 and band in (TrustBand.STABLE.value, TrustBand.HIGHLY_RELIABLE.value):
            suggestions.append(f"{sub} is stable and trusted — maintain current configuration")
        elif band == TrustBand.LOW_CONFIDENCE.value:
            suggestions.append(f"{sub} is low confidence — require human confirmation before acting")

    for row in signal_rankings[:5]:
        if float(row.get("usefulness_score") or 0) >= 0.7:
            suggestions.append(
                f"signal {row['signal']} is highly useful (precision {row['precision']:.0%})",
            )
        elif float(row.get("ignore_ratio") or 0) >= 0.6:
            suggestions.append(
                f"signal {row['signal']} is frequently ignored — candidate for suppression review",
            )

    for cand in retirement_candidates[:4]:
        suggestions.append(
            f"[{cand['label']}] {cand['signal']}: {cand['reason']}",
        )

    pulse = runtime.get("pulse") or {}
    if float(pulse.get("event_loop_lag_max") or 0) > 0.5:
        suggestions.append("runtime event-loop lag elevated during week — review ingest batching")
    if runtime.get("stability", {}).get("stalled_loops", 0) > 0:
        suggestions.append("runtime watchdog flagged stalled loops — verify loop registry health")

    for pat in incident_patterns[:3]:
        if pat.get("severity") == "important":
            suggestions.append(f"recurring pattern: {pat['pattern']} ({pat['occurrences']}×) — {pat['hint']}")

    if any("quarantine" in s.lower() or "source" in s.lower() for s in suggestions):
        pass
    else:
        for pat in incident_patterns:
            if pat.get("pattern") == "source_degradation" and pat.get("occurrences", 0) >= 2:
                suggestions.append("source quarantine thresholds may be too aggressive — review trust bands")
                break

    seen: set[str] = set()
    unique: list[str] = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:20]
