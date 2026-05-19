from __future__ import annotations

from typing import Any

from bot.live_ops.repository import LiveChannelRepository


class AudienceSafety:
    """Audience fatigue and engagement-derived safety signals."""

    def __init__(self, repository: LiveChannelRepository) -> None:
        self.repository = repository

    def observe_engagement(self, *, engagement: float, silence_rate: float) -> None:
        self.repository.record_feedback("engagement", engagement)
        self.repository.record_feedback("silence_rate", silence_rate)
        fatigue = min(1.0, silence_rate * 0.6 + max(0.0, 0.5 - engagement) * 0.8)
        self.repository.record_feedback("audience_fatigue", fatigue)

    def fatigue_score(self) -> float:
        state = self.repository.get_state() or {}
        detail = state.get("detail_json")
        if isinstance(detail, str):
            import json

            try:
                detail = json.loads(detail)
            except json.JSONDecodeError:
                detail = {}
        if isinstance(detail, dict):
            return float(detail.get("audience_fatigue", 0.2))
        return 0.2

    def should_throttle(self) -> bool:
        return self.fatigue_score() > 0.75
