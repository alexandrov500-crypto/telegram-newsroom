from __future__ import annotations

from collections import Counter
from typing import Any


def discover_incident_patterns(
    timeline: list[dict[str, Any]],
    *,
    min_occurrences: int = 3,
) -> list[dict[str, Any]]:
    """Recurring operational patterns from forensics timeline."""
    by_type: Counter[str] = Counter()
    by_detail: Counter[str] = Counter()
    lag_spikes = 0
    format_failures = 0
    rss_burst = 0
    storyline_sat = 0
    source_degrade = 0

    for ev in timeline:
        et = str(ev.get("event_type") or "")
        by_type[et] += 1
        details = ev.get("details") or {}
        detail_key = str(details.get("kind") or details.get("reason") or et)[:80]
        by_detail[detail_key] += 1

        blob = f"{et} {details}".lower()
        if "lag" in blob or "stalled" in blob:
            lag_spikes += 1
        if "format" in blob or "telegram" in blob and "fail" in blob:
            format_failures += 1
        if "rss" in blob or "ingest" in blob and "burst" in blob:
            rss_burst += 1
        if "saturation" in blob or "storyline" in blob and "satur" in blob:
            storyline_sat += 1
        if "quarantine" in blob or "source" in blob and "degrad" in blob:
            source_degrade += 1

    patterns: list[dict[str, Any]] = []

    def _add(name: str, count: int, severity: str, hint: str) -> None:
        if count >= min_occurrences:
            patterns.append(
                {
                    "pattern": name,
                    "occurrences": count,
                    "severity": severity,
                    "hint": hint,
                },
            )

    _add("event_loop_lag_spikes", lag_spikes, "important", "Review RSS batching and loop health during bursts")
    _add("formatting_failures", format_failures, "important", "Check editorial templates and Telegram HTML limits")
    _add("rss_ingest_bursts", rss_burst, "info", "Consider ingest throttle during peak feeds")
    _add("storyline_saturation", storyline_sat, "info", "Review narrative memory saturation thresholds")
    _add("source_degradation", source_degrade, "important", "Review source quarantine and trust calibration")

    for et, count in by_type.most_common(8):
        if count >= min_occurrences and et not in {p["pattern"] for p in patterns}:
            patterns.append(
                {
                    "pattern": et,
                    "occurrences": count,
                    "severity": "info",
                    "hint": f"Recurring event_type '{et}' — review runbook",
                },
            )

    recurring_false_pos: list[str] = []
    fp_counter: Counter[str] = Counter()
    for ev in timeline:
        if ev.get("event_type") == "warning_outcome" or "false_positive" in str(ev.get("details", {})):
            sub = str((ev.get("details") or {}).get("subsystem") or "unknown")
            fp_counter[sub] += 1
    for sub, c in fp_counter.items():
        if c >= min_occurrences:
            recurring_false_pos.append(sub)

    if recurring_false_pos:
        patterns.append(
            {
                "pattern": "recurring_false_positives",
                "occurrences": sum(fp_counter[s] for s in recurring_false_pos),
                "severity": "important",
                "hint": f"Subsystems with repeated false positives: {', '.join(recurring_false_pos[:5])}",
                "subsystems": recurring_false_pos,
            },
        )

    patterns.sort(key=lambda x: (-x["occurrences"], x["pattern"]))
    return patterns[:15]
