from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.live_ops.repository import LiveChannelRepository
from bot.runtime.state import runtime_state


class RollbackControl:
    """Batch rollback markers — advisory; sets shadow + pause."""

    def __init__(
        self,
        repository: LiveChannelRepository,
        *,
        enabled: bool = True,
    ) -> None:
        self.repository = repository
        self.enabled = enabled

    def rollback_last_batch(self, *, count: int = 5, reason: str = "operator") -> dict[str, Any]:
        if not self.enabled:
            return {"rolled_back": 0, "shadow": False, "paused": False, "disabled": True}
        runtime_state.shadow_publish_only = True
        now = datetime.now(timezone.utc).isoformat()
        self.repository.update_state(
            paused=1,
            last_rollback_at=now,
            live_mode="shadow",
        )
        self.repository.log_publish(
            pending_news_id=0,
            channel_id=None,
            live_mode="shadow",
            action="rollback_batch",
            passed=True,
            detail={"reason": reason, "batch_count": count},
        )
        self.repository.record_incident(
            "rollback_batch",
            "high",
            {"reason": reason, "count": count},
        )
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            record_timeline(
                "rollback_batch",
                severity="high",
                details={"count": count, "reason": reason},
            )
            record_audit("rollback_batch", payload={"count": count, "reason": reason})
        except Exception:
            pass
        return {"rolled_back": count, "shadow": True, "paused": True}

    def recent_rollback_count(self) -> int:
        return self.repository.rollback_count_24h()
