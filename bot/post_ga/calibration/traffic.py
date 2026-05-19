from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from bot.post_ga.repository import PostGaRepository


@dataclass
class LiveTrafficCalibrator:
    """Adaptive pacing from engagement, fatigue, overload cooldown."""

    repository: PostGaRepository
    _engagement: deque[float] = field(default_factory=lambda: deque(maxlen=48))
    _publishes: deque[float] = field(default_factory=lambda: deque(maxlen=48))
    _channel_fatigue: dict[int, float] = field(default_factory=dict)
    _cooldown_until: float = 0.0
    recommended_pacing_factor: float = 1.0

    def record_publish(self, *, channel_id: int | None = None, engagement: float = 0.5) -> None:
        now = time.monotonic()
        self._publishes.append(now)
        self._engagement.append(engagement)
        if channel_id is not None:
            self._channel_fatigue[channel_id] = self._channel_fatigue.get(channel_id, 0.0) + 0.1

    def record_telegram_pressure(self, *, floodwait: bool = False) -> None:
        if floodwait:
            self._cooldown_until = time.monotonic() + 120.0
            self.recommended_pacing_factor = 0.5

    def calibrate(
        self,
        *,
        queue_depth: int = 0,
        trust_score: float = 0.85,
        multilingual_skew: float = 0.0,
    ) -> dict[str, Any]:
        if time.monotonic() < self._cooldown_until:
            self.recommended_pacing_factor = 0.4
        elif queue_depth > 400:
            self.recommended_pacing_factor = 0.6
            self._cooldown_until = time.monotonic() + 60.0
        else:
            avg_eng = sum(self._engagement) / len(self._engagement) if self._engagement else 0.5
            if avg_eng < 0.35:
                self.recommended_pacing_factor = max(0.5, self.recommended_pacing_factor * 0.95)
            elif avg_eng > 0.7:
                self.recommended_pacing_factor = min(1.2, self.recommended_pacing_factor * 1.02)
            self.recommended_pacing_factor *= max(0.5, trust_score)
            if multilingual_skew > 0.4:
                self.recommended_pacing_factor *= 0.9

        audience = sum(self._engagement) / len(self._engagement) if self._engagement else 0.5
        hour_pubs = len([t for t in self._publishes if time.monotonic() - t < 3600])
        efficiency = min(1.0, audience / max(0.1, hour_pubs / 20.0)) if hour_pubs else audience

        pacing = {
            "factor": round(self.recommended_pacing_factor, 3),
            "hour_publishes": hour_pubs,
            "low_engagement_suppress": audience < 0.35,
            "fatigued_channels": sum(1 for v in self._channel_fatigue.values() if v > 2.0),
        }
        self.repository.save_calibration(audience=audience, efficiency=efficiency, pacing=pacing)
        return {
            "audience_responsiveness": round(audience, 3),
            "publish_efficiency": round(efficiency, 3),
            "pacing": pacing,
            "recommendation": self._pacing_hint(),
        }

    def _pacing_hint(self) -> str:
        if self.recommended_pacing_factor < 0.5:
            return "reduce_rate_cooldown"
        if self.recommended_pacing_factor > 1.05:
            return "slight_increase_ok"
        return "hold_current_pacing"

    def summary_text(self) -> str:
        row = self.repository.get_calibration() or {}
        lines = [
            "<b>Traffic calibration</b>",
            f"Audience {row.get('audience_responsiveness', 0):.2f} · "
            f"Efficiency {row.get('publish_efficiency', 0):.2f}",
            f"Pacing factor {self.recommended_pacing_factor:.2f}",
        ]
        p = row.get("pacing", {})
        if p.get("low_engagement_suppress"):
            lines.append("⚠️ Low engagement — suppressing low-value publishes")
        return "\n".join(lines)

    def audience_health_text(self) -> str:
        cal = self.calibrate()
        emoji = "🟢" if cal["audience_responsiveness"] >= 0.6 else "🟡" if cal["audience_responsiveness"] >= 0.4 else "🔴"
        return (
            f"<b>{emoji} Audience health</b>\n"
            f"Responsiveness {cal['audience_responsiveness']:.0%}\n"
            f"Efficiency {cal['publish_efficiency']:.0%}\n"
            f"Hint: {cal['recommendation']}"
        )
