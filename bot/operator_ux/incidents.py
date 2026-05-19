from __future__ import annotations

from typing import Any

from bot.operator_ux.severity import AttentionSeverity, classify_drift_alert


def group_incidents(
    *,
    live_incidents: list[dict[str, Any]],
    drift_warnings: list[str],
    publish_failures: int,
    runtime_unstable: bool,
) -> list[dict[str, Any]]:
    """Incident-centric groupings for operator triage."""
    groups: list[dict[str, Any]] = []

    if runtime_unstable:
        groups.append(
            {
                "id": "runtime_instability",
                "title": "Runtime instability",
                "severity": AttentionSeverity.CRITICAL.value,
                "count": 1,
                "detail": "Elevated lag, stalled loops, or recovery activity",
            },
        )

    if publish_failures > 0:
        sev = AttentionSeverity.IMPORTANT if publish_failures >= 2 else AttentionSeverity.INFORMATIONAL
        groups.append(
            {
                "id": "publish_incidents",
                "title": "Publish incidents",
                "severity": sev.value,
                "count": publish_failures,
                "detail": f"{publish_failures} failed/hold publishes (24h)",
            },
        )

    for w in drift_warnings[:3]:
        groups.append(
            {
                "id": f"editorial_drift:{w[:24]}",
                "title": "Editorial drift",
                "severity": classify_drift_alert(w).value,
                "count": 1,
                "detail": w,
            },
        )

    by_type: dict[str, int] = {}
    for inc in live_incidents:
        key = str(inc.get("incident_type") or inc.get("title") or "incident")[:40]
        by_type[key] = by_type.get(key, 0) + 1
    for key, count in sorted(by_type.items(), key=lambda kv: -kv[1])[:5]:
        sev = AttentionSeverity.CRITICAL if count >= 3 else AttentionSeverity.IMPORTANT
        groups.append(
            {
                "id": f"live:{key}",
                "title": key,
                "severity": sev.value,
                "count": count,
                "detail": "Live channel incident",
            },
        )

    return groups
