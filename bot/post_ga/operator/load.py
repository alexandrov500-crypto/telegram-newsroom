from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OperatorLoadManager:
    """Alert ranking, dedup, actionable-only escalation."""

    _alerts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _actions_hour: int = 0
    _last_action_reset: float = field(default_factory=time.monotonic)
    attention_score: float = 1.0
    actionable_only: bool = False

    def ingest_alert(
        self,
        key: str,
        *,
        severity: str,
        title: str,
        remediation: str,
        importance: float = 0.5,
    ) -> bool:
        if key in self._alerts:
            return False
        if self.actionable_only and severity not in ("critical", "error"):
            return False
        self._alerts[key] = {
            "severity": severity,
            "title": title,
            "remediation": remediation,
            "importance": importance,
            "at": time.monotonic(),
        }
        return True

    def rank_alerts(self) -> list[dict[str, Any]]:
        ranked = sorted(
            self._alerts.values(),
            key=lambda a: (
                {"critical": 3, "error": 2, "warn": 1}.get(a["severity"], 0),
                a["importance"],
            ),
            reverse=True,
        )
        return ranked[:10]

    def record_operator_action(self) -> None:
        now = time.monotonic()
        if now - self._last_action_reset > 3600:
            self._actions_hour = 0
            self._last_action_reset = now
        self._actions_hour += 1
        self.attention_score = max(0.2, 1.0 - self._actions_hour / 80.0)

    def load_text(self) -> str:
        ranked = self.rank_alerts()
        lines = [
            "<b>Operator load</b>",
            f"Pending ranked: {len(ranked)} · attention {self.attention_score:.0%}",
            f"Actions/h: {self._actions_hour}",
        ]
        for a in ranked[:5]:
            lines.append(f"• [{a['severity']}] {a['title'][:50]}")
        if not ranked:
            lines.append("✅ No ranked alerts")
        return "\n".join(lines)

    def attention_risk_text(self) -> str:
        risk = 1.0 - self.attention_score
        emoji = "🟢" if risk < 0.3 else "🟡" if risk < 0.6 else "🔴"
        return (
            f"<b>{emoji} Attention risk</b>\n"
            f"Fatigue risk {risk:.0%} · {self._actions_hour} actions/h\n"
            f"Actionable-only: {'on' if self.actionable_only else 'off'}"
        )
