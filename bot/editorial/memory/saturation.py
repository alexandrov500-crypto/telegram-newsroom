from __future__ import annotations

from datetime import datetime, timezone


def compute_saturation(*, publish_count_72h: int, publish_count_total: int) -> float:
    """0–1 saturation; higher means audience may be fatigued on this storyline."""
    recent = min(1.0, publish_count_72h / 5.0)
    total = min(1.0, publish_count_total / 12.0)
    return round(max(recent * 0.7 + total * 0.3, 0.0), 3)


def hours_since(iso_ts: str) -> float:
    try:
        then = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0
    except ValueError:
        return 9999.0
