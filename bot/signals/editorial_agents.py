from __future__ import annotations

import logging

from bot.distributed.event_bus.base import DistributedEventBus
from bot.events.types import EventType, NewsroomEvent
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


class EditorialAgentRouter:
    """Lightweight event-driven agents for signal response."""

    def __init__(self, event_bus: DistributedEventBus) -> None:
        self._bus = event_bus
        self._register()

    def _register(self) -> None:
        self._bus.subscribe(EventType.SIGNAL_DETECTED.value, self._breaking_news_agent)
        self._bus.subscribe(EventType.SIGNAL_DETECTED.value, self._market_watch_agent)
        self._bus.subscribe(EventType.SIGNAL_DETECTED.value, self._geopolitical_agent)
        self._bus.subscribe(EventType.TREND_ESCALATED.value, self._trend_agent)
        self._bus.subscribe(EventType.PRIORITY_DECIDED.value, self._risk_review_agent)
        self._bus.subscribe(EventType.ANOMALY_DETECTED.value, self._fact_check_agent)
        self._bus.subscribe(EventType.IMPACT_FORECAST_GENERATED.value, self._digest_curator_agent)

    async def _breaking_news_agent(self, event: NewsroomEvent) -> None:
        payload = event.payload
        if payload.get("signal_type") not in (
            "geopolitical_escalation",
            "market_moving",
            "narrative_acceleration",
        ):
            return
        if float(payload.get("confidence", 0)) < 0.85:
            return
        logger.info(
            "event=agent_action agent=breaking_news signal_id=%s confidence=%.2f",
            payload.get("signal_id"),
            payload.get("confidence"),
        )
        runtime_state.last_breaking_signal_at = event.created_at
        runtime_state.signals_detected_session += 1

    async def _market_watch_agent(self, event: NewsroomEvent) -> None:
        if event.payload.get("signal_type") != "market_moving":
            return
        logger.info(
            "event=agent_action agent=market_watch signal_id=%s",
            event.payload.get("signal_id"),
        )

    async def _geopolitical_agent(self, event: NewsroomEvent) -> None:
        if event.payload.get("signal_type") != "geopolitical_escalation":
            return
        logger.info(
            "event=agent_action agent=geopolitical signal_id=%s",
            event.payload.get("signal_id"),
        )

    async def _trend_agent(self, event: NewsroomEvent) -> None:
        prob = float(event.payload.get("forecast_probability", 0))
        if prob < 0.7:
            return
        logger.info(
            "event=agent_action agent=trend story_id=%s probability=%.2f",
            event.payload.get("story_id"),
            prob,
        )

    async def _risk_review_agent(self, event: NewsroomEvent) -> None:
        action = str(event.payload.get("action", ""))
        if action not in ("escalate_admin", "wait_confirmation"):
            return
        logger.info(
            "event=agent_action agent=risk_review pending_news_id=%s action=%s score=%.2f",
            event.payload.get("pending_news_id"),
            action,
            float(event.payload.get("editorial_priority_score", 0)),
        )

    async def _fact_check_agent(self, event: NewsroomEvent) -> None:
        severity = float(event.payload.get("severity", 0))
        if severity < 0.6:
            return
        logger.info(
            "event=agent_action agent=fact_check anomaly=%s scope=%s severity=%.2f",
            event.payload.get("anomaly_type"),
            event.payload.get("scope_key"),
            severity,
        )

    async def _digest_curator_agent(self, event: NewsroomEvent) -> None:
        impact = float(event.payload.get("expected_impact", 0))
        if impact < 0.65:
            return
        logger.info(
            "event=agent_action agent=digest_curator story_id=%s impact=%.2f",
            event.payload.get("story_id"),
            impact,
        )
