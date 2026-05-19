from __future__ import annotations

from typing import Any

MAX_INCIDENTS = 40
MAX_RECOVERY_RECORDS = 30


def evict_incidents(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rolling eviction — keep most recent / highest occurrence."""
    if len(incidents) <= MAX_INCIDENTS:
        return incidents
    ranked = sorted(
        incidents,
        key=lambda x: (int(x.get("occurrences") or 0), -int(x.get("last_seen_days") or 999)),
        reverse=True,
    )
    return ranked[:MAX_INCIDENTS]


def evict_recoveries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(records) <= MAX_RECOVERY_RECORDS:
        return records
    return records[-MAX_RECOVERY_RECORDS:]
