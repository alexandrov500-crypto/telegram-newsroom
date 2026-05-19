from __future__ import annotations

from enum import Enum


class AlertLevel(str, Enum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "notice": 1, "warning": 2, "critical": 3}[self.value]

    def marker(self) -> str:
        return {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.NOTICE: "📋",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
        }[self]

    def badge(self) -> str:
        return f"{self.marker()} {self.value.upper()}"


def format_level_header(tag: str, level: AlertLevel) -> str:
    from bot.operator_console.formatting import escape

    return f"{level.marker()} <b>[{escape(tag)}]</b> {level.value.upper()}"


def incident_dedupe_key(kind: str, detail: str) -> str:
    """Stable key for routing duplicate incidents to one thread."""
    token = kind.lower().split("_")[0]
    for needle in ("replay", "contradiction", "federation", "topology", "misinfo", "confidence"):
        if needle in kind.lower() or needle in detail.lower():
            return f"incident:{needle}"
    return f"incident:{token[:24]}"


def critical_operator_mention(admin_ids: frozenset[int]) -> str:
    if not admin_ids:
        return ""
    mentions = " ".join(f'<a href="tg://user?id={uid}">op</a>' for uid in list(admin_ids)[:3])
    return f"\n{mentions}"


def score_ingest(*, priority: float, duplicate: bool) -> AlertLevel:
    if duplicate:
        return AlertLevel.INFO
    if priority >= 0.88:
        return AlertLevel.NOTICE
    if priority >= 0.75:
        return AlertLevel.INFO
    return AlertLevel.INFO


def score_cognitive(*, priority: float, contradiction_count: int, trust: float) -> AlertLevel:
    if contradiction_count > 5 or trust < 0.3:
        return AlertLevel.WARNING
    if priority >= 0.85:
        return AlertLevel.NOTICE
    return AlertLevel.INFO


def score_contradiction_burst(count: int, *, delta: int) -> AlertLevel:
    if count >= 25 or delta >= 15:
        return AlertLevel.CRITICAL
    if count >= 15 or delta >= 8:
        return AlertLevel.WARNING
    return AlertLevel.NOTICE


def score_incident(kind: str, *, open_contradictions: int = 0, mesh_health: float = 1.0) -> AlertLevel:
    if kind in ("replay_corruption", "data_loss", "publish_storm"):
        return AlertLevel.CRITICAL
    if mesh_health < 0.5 or open_contradictions > 30:
        return AlertLevel.CRITICAL
    if kind in ("confidence_runaway", "storage_acceleration", "federation_partition"):
        return AlertLevel.WARNING
    return AlertLevel.NOTICE
