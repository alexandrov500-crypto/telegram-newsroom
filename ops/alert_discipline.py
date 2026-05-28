"""Alert severity + cooldown discipline (Phase 3)."""

from __future__ import annotations

import os
import threading
import time
from enum import Enum

_lock = threading.RLock()
_last_sent: dict[str, float] = {}


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


def normalize_severity(raw: str) -> AlertSeverity:
    v = (raw or "info").strip().lower()
    if v in ("critical", "crit", "high"):
        return AlertSeverity.CRITICAL
    if v in ("warning", "warn", "medium"):
        return AlertSeverity.WARNING
    return AlertSeverity.INFO


def cooldown_sec(severity: AlertSeverity) -> float:
    base = float(os.getenv("NOTIFICATION_RATE_LIMIT_MINUTES", "15") or 15) * 60.0
    if severity == AlertSeverity.CRITICAL:
        return max(60.0, base * 0.5)
    if severity == AlertSeverity.WARNING:
        return base
    return max(base, 30 * 60.0)


def should_emit_alert(kind: str, *, severity: AlertSeverity, group_key: str = "") -> bool:
    """Return False when within cooldown for this kind+group."""
    key = f"{severity.value}:{kind}:{group_key or kind}"[:120]
    now = time.monotonic()
    window = cooldown_sec(severity)
    with _lock:
        last = _last_sent.get(key)
        if last is not None and (now - last) < window:
            return False
        _last_sent[key] = now
    return True


def reset_alert_discipline_for_tests() -> None:
    with _lock:
        _last_sent.clear()
