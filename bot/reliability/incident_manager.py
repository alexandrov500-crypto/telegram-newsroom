from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from bot.operations.incident_lifecycle import IncidentLifecycleManager, OpsIncident
from bot.operations.repository import OperationsRepository
from bot.reliability.types import IncidentSeverity

logger = logging.getLogger(__name__)

_SEVERITY_DB = {
    IncidentSeverity.INFO: "info",
    IncidentSeverity.WARN: "warning",
    IncidentSeverity.ERROR: "error",
    IncidentSeverity.CRITICAL: "critical",
    IncidentSeverity.FATAL: "fatal",
}


@dataclass(frozen=True)
class ProductionIncident:
    incident_id: str
    subsystem: str
    severity: IncidentSeverity
    summary: str
    context: dict[str, Any]
    recovery_status: str
    correlation_ids: list[str]


class ProductionIncidentManager:
    """Structured incidents with Telegram escalation and ingest pause on FATAL."""

    def __init__(
        self,
        lifecycle: IncidentLifecycleManager,
        repository: OperationsRepository,
    ) -> None:
        self._lifecycle = lifecycle
        self._repo = repository
        self._notify_handlers: list[Any] = []

    def on_notify(self, handler: Any) -> None:
        self._notify_handlers.append(handler)

    async def emit(
        self,
        *,
        title: str,
        severity: IncidentSeverity | str,
        subsystem: str,
        summary: str | None = None,
        detail: str = "",
        correlation_key: str,
        correlation_ids: list[str] | None = None,
        replay_refs: list[str] | None = None,
        suggested_action: str | None = None,
        recovery_status: str = "none",
        context: dict[str, Any] | None = None,
    ) -> ProductionIncident:
        if isinstance(severity, str):
            severity = IncidentSeverity[severity.upper()]
        body = {
            "subsystem": subsystem,
            "summary": summary or title,
            "context": context or {},
            "recovery_status": recovery_status,
            "correlation_ids": correlation_ids or [],
        }
        detail_text = json.dumps(body, default=str)[:2000]
        if detail:
            detail_text = f"{detail}\n{detail_text}"

        inc: OpsIncident = self._lifecycle.open_incident(
            title=title,
            severity=_SEVERITY_DB.get(severity, "warning"),
            detail=detail_text,
            correlation_key=correlation_key,
            replay_refs=replay_refs,
            suggested_action=suggested_action,
        )
        prod = ProductionIncident(
            incident_id=inc.incident_id,
            subsystem=subsystem,
            severity=severity,
            summary=summary or title,
            context=body["context"],
            recovery_status=recovery_status,
            correlation_ids=correlation_ids or [],
        )
        logger.warning(
            "event=production_incident incident_id=%s severity=%s subsystem=%s",
            prod.incident_id,
            severity.value,
            subsystem,
        )
        for handler in self._notify_handlers:
            try:
                await handler(prod)
            except Exception:
                logger.exception("event=incident_notify_handler_failed")
        return prod

    def recent_fatal_count(self, hours: int = 24) -> int:
        rows = self._repo.list_incidents(status=None, limit=50)
        count = 0
        for r in rows:
            if r.get("severity") == "fatal" and r.get("status") != "resolved":
                count += 1
        return count

    def format_telegram_alert(self, inc: ProductionIncident) -> str:
        emoji = {
            IncidentSeverity.INFO: "ℹ️",
            IncidentSeverity.WARN: "⚠️",
            IncidentSeverity.ERROR: "🔴",
            IncidentSeverity.CRITICAL: "🚨",
            IncidentSeverity.FATAL: "⛔",
        }.get(inc.severity, "•")
        lines = [
            f"{emoji} <b>{inc.severity.value}</b> · {inc.subsystem}",
            f"<code>{inc.incident_id}</code>",
            inc.summary[:280],
        ]
        if inc.recovery_status != "none":
            lines.append(f"Recovery: {inc.recovery_status}")
        if inc.correlation_ids:
            refs = ", ".join(inc.correlation_ids[:3])
            lines.append(f"Refs: <code>{refs}</code>")
        lines.append("/incidents_live · /recovery_live")
        return "\n".join(lines)
