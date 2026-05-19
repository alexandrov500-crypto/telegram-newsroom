from __future__ import annotations

import os
from datetime import datetime, timezone

from bot.operator_ux.severity import AttentionSeverity


def quiet_mode_enabled() -> bool:
    raw = os.getenv("OPS_QUIET_MODE", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _quiet_hours() -> tuple[int | None, int | None]:
    start = os.getenv("OPS_QUIET_HOUR_START", "").strip()
    end = os.getenv("OPS_QUIET_HOUR_END", "").strip()
    try:
        return (int(start), int(end)) if start and end else (None, None)
    except ValueError:
        return None, None


def in_quiet_window() -> bool:
    start, end = _quiet_hours()
    if start is None or end is None:
        return False
    hour = datetime.now(timezone.utc).hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def should_deliver(severity: AttentionSeverity, *, force: bool = False) -> bool:
    """Critical always delivers; quiet mode suppresses non-critical."""
    if force or severity == AttentionSeverity.CRITICAL:
        return True
    if quiet_mode_enabled() and in_quiet_window():
        return severity.rank >= AttentionSeverity.IMPORTANT.rank
    if quiet_mode_enabled():
        return severity.rank >= AttentionSeverity.INFORMATIONAL.rank
    return True
