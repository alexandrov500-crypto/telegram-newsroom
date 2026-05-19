from __future__ import annotations

from bot.live_ops.channel_settings import LiveMode
from bot.live_ops.repository import LiveChannelRepository


class OperatorOverride:
    """Operator pause/resume/mode overrides."""

    def __init__(self, repository: LiveChannelRepository) -> None:
        self.repository = repository
        self._manual_freeze = False

    def pause_live(self) -> None:
        self.repository.update_state(paused=1)

    def resume_live(self) -> None:
        self.repository.update_state(paused=0, frozen=0, failures_recent=0, cooldown_until=None)
        self._manual_freeze = False
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            record_timeline("resume_live", severity="info", details={})
            record_audit("resume_live", payload={})
        except Exception:
            pass

    def freeze_publishing(self) -> None:
        self._manual_freeze = True
        self.repository.update_state(frozen=1, paused=1)
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            record_timeline("freeze_publishing", severity="warning", details={"source": "operator_override"})
            record_audit("freeze_publishing", payload={"source": "operator_override"})
        except Exception:
            pass

    def is_frozen(self) -> bool:
        return self._manual_freeze

    def set_mode(self, mode: LiveMode) -> None:
        self.repository.update_state(live_mode=mode.value)

    def mark_post(self, *, pending_news_id: int, good: bool, operator_id: int | None = None) -> None:
        self.repository.rate_post(
            pending_news_id=pending_news_id,
            rating="good" if good else "bad",
            operator_id=operator_id,
        )
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            action = "mark_good_post" if good else "mark_bad_post"
            record_timeline(
                action,
                severity="info",
                details={"operator_id": operator_id},
                publish_id=pending_news_id,
            )
            record_audit(
                action,
                actor=str(operator_id) if operator_id else None,
                publish_id=pending_news_id,
                payload={"good": good, "operator_id": operator_id},
            )
        except Exception:
            pass
        try:
            from bot.trust_calibration.service import record_operator_rating

            record_operator_rating(
                pending_news_id=pending_news_id,
                good=good,
                operator_id=operator_id,
            )
        except Exception:
            pass
