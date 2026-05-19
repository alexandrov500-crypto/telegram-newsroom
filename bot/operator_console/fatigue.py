from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.operator_console.severity import AlertLevel


@dataclass
class FatigueSnapshot:
    score: float
    messages_last_hour: int
    alerts_last_hour: int
    digest_mode: bool
    suppressed_last_hour: int
    load_label: str
    quiet_window: bool
    overload_warning: bool
    repeated_categories: dict[str, int]


class FatigueGuard:
    """Anti-fatigue: adaptive suppression without hiding CRITICAL."""

    def __init__(
        self,
        *,
        max_messages_per_hour: int = 45,
        max_alerts_per_hour: int = 25,
        fatigue_threshold: float = 0.72,
        quiet_hour_start: int | None = None,
        quiet_hour_end: int | None = None,
    ) -> None:
        self._max_msg = max_messages_per_hour
        self._max_alerts = max_alerts_per_hour
        self._threshold = fatigue_threshold
        self._quiet_start = quiet_hour_start
        self._quiet_end = quiet_hour_end
        self._send_times: deque[float] = deque()
        self._alert_times: deque[float] = deque()
        self._category_times: dict[str, deque[float]] = {}
        self._suppressed = 0
        self._digest_mode = False
        self._burst_collapses = 0
        self._incident_counts: dict[str, int] = {}
        self._last_operator_action: float | None = None

    def _prune(self, q: deque[float], window: float = 3600.0) -> None:
        now = time.monotonic()
        while q and now - q[0] > window:
            q.popleft()

    def in_quiet_window(self) -> bool:
        if self._quiet_start is None or self._quiet_end is None:
            return False
        hour = datetime.now(timezone.utc).hour
        start, end = self._quiet_start, self._quiet_end
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def record_send(self, *, is_alert: bool = False, category: str = "general") -> None:
        now = time.monotonic()
        self._send_times.append(now)
        if is_alert:
            self._alert_times.append(now)
        cat_q = self._category_times.setdefault(category, deque())
        cat_q.append(now)
        self._prune(cat_q)
        self._prune(self._send_times)
        self._prune(self._alert_times)
        self._update_digest_mode()
        self._publish_fatigue_metric()

    def record_suppressed(self) -> None:
        self._suppressed += 1

    def record_operator_action(self) -> None:
        self._last_operator_action = time.monotonic()

    def record_incident_type(self, kind: str) -> None:
        self._incident_counts[kind] = self._incident_counts.get(kind, 0) + 1

    def _update_digest_mode(self) -> None:
        self._prune(self._send_times)
        self._prune(self._alert_times)
        overload = (
            len(self._send_times) >= self._max_msg
            or len(self._alert_times) >= self._max_alerts
        )
        self._digest_mode = overload or self.in_quiet_window()

    def should_suppress(self, level: AlertLevel) -> bool:
        if level == AlertLevel.CRITICAL:
            return False
        if level == AlertLevel.WARNING and not self._digest_mode:
            return False
        if self._digest_mode and level in (AlertLevel.INFO, AlertLevel.NOTICE):
            return True
        if self.in_quiet_window() and level == AlertLevel.INFO:
            return True
        return False

    def enter_quiet_burst_collapse(self) -> bool:
        if self._digest_mode:
            self._burst_collapses += 1
            try:
                from bot.observability.metrics import record_operator_burst_collapse

                record_operator_burst_collapse()
            except Exception:
                pass
            return True
        return False

    @property
    def burst_collapses(self) -> int:
        return self._burst_collapses

    def snapshot(self) -> FatigueSnapshot:
        self._prune(self._send_times)
        self._prune(self._alert_times)
        msg_h = len(self._send_times)
        alert_h = len(self._alert_times)
        ratio = min(1.0, msg_h / max(self._max_msg, 1))
        alert_ratio = min(1.0, alert_h / max(self._max_alerts, 1))
        score = round(0.6 * ratio + 0.4 * alert_ratio, 3)
        if score < 0.35:
            load = "low"
        elif score < 0.65:
            load = "moderate"
        elif score < 0.85:
            load = "elevated"
        else:
            load = "high"
        repeated = {
            cat: len(q)
            for cat, q in self._category_times.items()
            if len(q) >= 5
        }
        return FatigueSnapshot(
            score=score,
            messages_last_hour=msg_h,
            alerts_last_hour=alert_h,
            digest_mode=self._digest_mode,
            suppressed_last_hour=self._suppressed,
            load_label=load,
            quiet_window=self.in_quiet_window(),
            overload_warning=score >= self._threshold,
            repeated_categories=repeated,
        )

    def _publish_fatigue_metric(self) -> None:
        try:
            from bot.observability.metrics import set_operator_fatigue_score

            set_operator_fatigue_score(self.snapshot().score)
        except Exception:
            pass
