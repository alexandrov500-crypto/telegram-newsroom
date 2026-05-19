from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bot.production_safety.repository import ProductionSafetyRepository
from bot.production_safety.settings import ProductionSafetySettings

logger = logging.getLogger(__name__)


class OperatorFailoverManager:
    """Multi-operator heartbeat, silent-operator detection, escalation hints."""

    def __init__(
        self,
        settings: ProductionSafetySettings,
        repository: ProductionSafetyRepository,
        *,
        admin_ids: frozenset[int],
        backup_chat_id: int | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._admin_ids = admin_ids
        self._backup_chat_id = backup_chat_id

    def record_activity(self, operator_id: str, *, command: str | None = None) -> None:
        self._repo.operator_heartbeat(operator_id, command=command)

    def silent_operators(self) -> list[dict[str, Any]]:
        rows = self._repo.list_operator_heartbeats()
        silent: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for r in rows:
            try:
                seen = datetime.fromisoformat(str(r["last_seen_at"]).replace("Z", "+00:00"))
                hours = (now - seen).total_seconds() / 3600.0
                if hours >= self._settings.operator_silent_hours:
                    silent.append({**r, "silent_hours": round(hours, 1)})
            except Exception:
                continue
        for aid in self._admin_ids:
            if not any(str(r.get("operator_id")) == str(aid) for r in rows):
                silent.append({"operator_id": str(aid), "silent_hours": 999, "never_seen": True})
        return silent

    def escalation_summary(self) -> str:
        silent = self.silent_operators()
        lines = ["<b>Operator failover</b>", f"Admins configured: {len(self._admin_ids)}"]
        if self._backup_chat_id:
            lines.append(f"Backup chat: <code>{self._backup_chat_id}</code>")
        if not silent:
            lines.append("All operators active ✅")
        else:
            lines.append("⚠️ Silent operators:")
            for s in silent[:6]:
                lines.append(
                    f"• <code>{s.get('operator_id')}</code> "
                    f"{s.get('silent_hours', '?')}h",
                )
        return "\n".join(lines)
