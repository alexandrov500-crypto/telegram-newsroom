from __future__ import annotations

from enum import Enum

from bot.operator_console.severity import AlertLevel


class AttentionSeverity(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"
    BACKGROUND = "background"

    @property
    def rank(self) -> int:
        return {
            "critical": 4,
            "important": 3,
            "informational": 2,
            "background": 1,
        }[self.value]

    def marker(self) -> str:
        return {
            AttentionSeverity.CRITICAL: "🚨",
            AttentionSeverity.IMPORTANT: "⚠️",
            AttentionSeverity.INFORMATIONAL: "ℹ️",
            AttentionSeverity.BACKGROUND: "·",
        }[self]

    def to_alert_level(self) -> AlertLevel:
        return {
            AttentionSeverity.CRITICAL: AlertLevel.CRITICAL,
            AttentionSeverity.IMPORTANT: AlertLevel.WARNING,
            AttentionSeverity.INFORMATIONAL: AlertLevel.NOTICE,
            AttentionSeverity.BACKGROUND: AlertLevel.INFO,
        }[self]

    @classmethod
    def from_alert_level(cls, level: AlertLevel) -> AttentionSeverity:
        return {
            AlertLevel.CRITICAL: cls.CRITICAL,
            AlertLevel.WARNING: cls.IMPORTANT,
            AlertLevel.NOTICE: cls.INFORMATIONAL,
            AlertLevel.INFO: cls.BACKGROUND,
        }[level]


def classify_runtime_anomaly(anomaly: dict) -> AttentionSeverity:
    level = str(anomaly.get("level") or anomaly.get("severity") or "").lower()
    if level in ("critical", "error"):
        return AttentionSeverity.CRITICAL
    if level in ("warning", "warn"):
        return AttentionSeverity.IMPORTANT
    return AttentionSeverity.INFORMATIONAL


def classify_editorial_warning(warning: str) -> AttentionSeverity:
    w = warning.lower()
    if any(k in w for k in ("contradict", "framing differ", "saturation high")):
        return AttentionSeverity.IMPORTANT
    if any(k in w for k in ("duplicate", "low editorial", "low-signal", "fatigue")):
        return AttentionSeverity.INFORMATIONAL
    return AttentionSeverity.BACKGROUND


def classify_drift_alert(alert: str) -> AttentionSeverity:
    a = alert.lower()
    if "rising_noise" in a or "overbreaking" in a or "quality_drift" in a:
        return AttentionSeverity.IMPORTANT
    return AttentionSeverity.INFORMATIONAL


def min_severity(*levels: AttentionSeverity) -> AttentionSeverity:
    return max(levels, key=lambda s: s.rank)
