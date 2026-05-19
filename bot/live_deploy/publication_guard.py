from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.live_deploy.first_72h import First72HMode
from bot.live_deploy.repository import LiveDeployRepository
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LivePublishVerdict:
    allowed: bool
    route_shadow: bool
    reason: str
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "route_shadow": self.route_shadow,
            "reason": self.reason,
            "blockers": list(self.blockers),
        }


@dataclass
class LivePublicationGuard:
    """Pre-public publish gate — routes to shadow/quarantine on failure."""

    repository: LiveDeployRepository
    first_72h: First72HMode

    def evaluate(
        self,
        *,
        pending_news_id: int,
        quality_score: float,
        trust_score: float,
        publish_confidence: float | None,
        operator_approved: bool,
        signals: dict[str, Any] | None = None,
    ) -> LivePublishVerdict:
        sig = signals or {}
        blockers: list[str] = []
        thr = self.first_72h.thresholds()

        if runtime_state.shadow_publish_only:
            return LivePublishVerdict(True, True, "shadow_mode", ())

        if sig.get("governance_frozen") or sig.get("freeze_active"):
            blockers.append("governance_freeze")
        if sig.get("war_room_active"):
            blockers.append("war_room_active")
        if sig.get("campaign_active") and float(sig.get("publish_pressure", 0)) > 0.85:
            blockers.append("campaign_overload")
        if float(sig.get("slo_burn", 0)) > 0.15:
            blockers.append("slo_burn")
        if sig.get("retry_amplification"):
            blockers.append("retry_amplification")
        if float(sig.get("telegram_pressure", 0)) > 0.8:
            blockers.append("telegram_pressure")
        if not sig.get("ga_healthy", True):
            blockers.append("ga_degraded")
        if sig.get("rollback_in_progress"):
            blockers.append("rollback_in_progress")

        if quality_score < thr["min_quality"]:
            blockers.append(f"quality_below_{thr['min_quality']:.2f}")
        if trust_score < thr["min_trust"]:
            blockers.append(f"trust_below_{thr['min_trust']:.2f}")
        conf = publish_confidence if publish_confidence is not None else trust_score
        if conf < thr["min_confidence"]:
            blockers.append(f"confidence_below_{thr['min_confidence']:.2f}")
        if thr["mandatory_approval"] and not operator_approved:
            blockers.append("operator_approval_required")

        allowed = len(blockers) == 0
        route_shadow = not allowed
        reason = "ok" if allowed else f"live_guard:{blockers[0]}"

        self.repository.audit_publish(
            pending_news_id=pending_news_id,
            action="public_publish",
            passed=allowed,
            blockers=blockers,
            detail={"quality": quality_score, "trust": trust_score, "confidence": conf},
        )

        if not allowed:
            logger.warning(
                "event=live_publication_guard_block pending_news_id=%d blockers=%s",
                pending_news_id,
                blockers,
            )

        return LivePublishVerdict(
            allowed=allowed,
            route_shadow=route_shadow,
            reason=reason,
            blockers=tuple(blockers),
        )
