from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bot.operator_console.formatting import clamp_lines, format_header, severity_marker


@dataclass
class PendingAlert:
    key: str
    severity: str
    title: str
    body: str
    remediation: str
    at: float = field(default_factory=time.monotonic)


@dataclass
class OperatorUxHub:
    """Alert dedup, digest mode, quiet hours, escalation batching."""

    quiet_hour_start: int | None = None
    quiet_hour_end: int | None = None
    digest_mode: bool = False
    _pending: dict[str, PendingAlert] = field(default_factory=dict)
    _acked: set[str] = field(default_factory=set)
    _history: deque[str] = field(default_factory=lambda: deque(maxlen=50))

    def in_quiet_hours(self) -> bool:
        if self.quiet_hour_start is None or self.quiet_hour_end is None:
            return False
        hour = datetime.now(timezone.utc).hour
        start, end = self.quiet_hour_start, self.quiet_hour_end
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def enqueue_alert(
        self,
        key: str,
        *,
        severity: str,
        title: str,
        body: str,
        remediation: str,
    ) -> bool:
        if key in self._acked:
            return False
        self._pending[key] = PendingAlert(
            key=key,
            severity=severity,
            title=title,
            body=body,
            remediation=remediation,
        )
        return True

    def acknowledge(self, key: str) -> None:
        self._acked.add(key)
        self._pending.pop(key, None)

    def format_alert(self, alert: PendingAlert) -> str:
        lines = [
            format_header(alert.title, alert.severity),
            clamp_lines(alert.body, max_lines=6),
            f"<i>→ {alert.remediation}</i>",
        ]
        return "\n".join(lines)

    def critical_batch(self) -> str:
        critical = [a for a in self._pending.values() if a.severity in ("critical", "error")]
        if not critical:
            return "No critical alerts pending."
        lines = [f"<b>{severity_marker('critical')} Critical ({len(critical)})</b>"]
        for a in critical[:5]:
            lines.append(f"• {a.title}: {a.body[:60]}…")
            lines.append(f"  → {a.remediation[:50]}")
        return "\n".join(lines)

    def digest_text(self) -> str:
        if not self._pending:
            return "✅ Operator digest: no pending alerts."
        by_sev: dict[str, list[PendingAlert]] = {}
        for a in self._pending.values():
            by_sev.setdefault(a.severity, []).append(a)
        lines = ["<b>Operator digest</b>"]
        for sev in ("critical", "error", "warn", "info"):
            group = by_sev.get(sev, [])
            if group:
                lines.append(f"{severity_marker(sev)} {sev}: {len(group)}")
        return "\n".join(lines)

    def what_changed(self, previous: dict[str, Any], current: dict[str, Any]) -> str:
        changes: list[str] = []
        for k in sorted(set(previous) | set(current)):
            if previous.get(k) != current.get(k):
                changes.append(f"{k}: {previous.get(k)} → {current.get(k)}")
        if not changes:
            return "No material changes."
        return "Changes:\n" + "\n".join(f"• {c}" for c in changes[:8])
