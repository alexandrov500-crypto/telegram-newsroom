from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from bot.ga_ops.repository import GaOpsRepository
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


class TrafficPressure(str, Enum):
    PUBLIC_TRAFFIC_SAFE = "PUBLIC_TRAFFIC_SAFE"
    TRAFFIC_PRESSURE_HIGH = "TRAFFIC_PRESSURE_HIGH"
    TRAFFIC_PRESSURE_CRITICAL = "TRAFFIC_PRESSURE_CRITICAL"


@dataclass
class PublishGuardrailVerdict:
    allowed: bool
    pressure: TrafficPressure
    reason: str
    max_rate_per_hour: int


@dataclass
class PublicTrafficGuardrails:
    """GA publish pacing: surge, spam, trust-weighted limits, global freeze."""

    repository: GaOpsRepository
    max_publishes_per_hour: int = 40
    surge_queue_threshold: int = 300
    _publish_timestamps: list[float] = field(default_factory=list)
    _narrative_hashes: set[str] = field(default_factory=set)
    _lang_counts: dict[str, int] = field(default_factory=dict)
    global_freeze: bool = False

    def record_publish(self, *, language: str = "en", narrative_key: str | None = None) -> None:
        now = time.monotonic()
        self._publish_timestamps.append(now)
        hour_ago = now - 3600
        self._publish_timestamps = [t for t in self._publish_timestamps if t >= hour_ago]
        self._lang_counts[language] = self._lang_counts.get(language, 0) + 1
        if narrative_key:
            self._narrative_hashes.add(narrative_key[:64])

    def emergency_freeze(self, *, active: bool = True) -> None:
        self.global_freeze = active
        if active:
            runtime_state.ingestion_paused = True
            logger.critical("event=ga_global_publish_freeze")

    def evaluate(
        self,
        *,
        queue_depth: int = 0,
        trust_score: float = 0.85,
        breaking_news: bool = False,
        narrative_key: str | None = None,
        language: str = "en",
    ) -> PublishGuardrailVerdict:
        if self.global_freeze:
            return PublishGuardrailVerdict(
                allowed=False,
                pressure=TrafficPressure.TRAFFIC_PRESSURE_CRITICAL,
                reason="global_freeze",
                max_rate_per_hour=0,
            )

        hour_count = len(self._publish_timestamps)
        trust_factor = max(0.3, min(1.0, trust_score))
        effective_cap = int(self.max_publishes_per_hour * trust_factor)
        if breaking_news:
            effective_cap = min(effective_cap + 6, self.max_publishes_per_hour + 10)

        pressure = TrafficPressure.PUBLIC_TRAFFIC_SAFE
        if queue_depth >= self.surge_queue_threshold or hour_count >= effective_cap * 0.85:
            pressure = TrafficPressure.TRAFFIC_PRESSURE_HIGH
        if queue_depth >= self.surge_queue_threshold * 1.5 or hour_count >= effective_cap:
            pressure = TrafficPressure.TRAFFIC_PRESSURE_CRITICAL

        if narrative_key and narrative_key[:64] in self._narrative_hashes:
            return PublishGuardrailVerdict(
                allowed=False,
                pressure=pressure,
                reason="duplicate_narrative",
                max_rate_per_hour=effective_cap,
            )

        langs = list(self._lang_counts.values())
        if langs and max(langs) - min(langs) > effective_cap // 2:
            dominant = max(self._lang_counts, key=self._lang_counts.get)  # type: ignore
            if language == dominant and hour_count > effective_cap * 0.7:
                return PublishGuardrailVerdict(
                    allowed=False,
                    pressure=pressure,
                    reason="multilingual_imbalance",
                    max_rate_per_hour=effective_cap,
                )

        allowed = pressure != TrafficPressure.TRAFFIC_PRESSURE_CRITICAL and hour_count < effective_cap
        reason = "ok" if allowed else "rate_or_surge_limit"
        self.repository.set_traffic_state(
            pressure_level=pressure.value,
            publishes_hour=hour_count,
            global_freeze=self.global_freeze,
            detail={"queue": queue_depth, "cap": effective_cap},
        )
        return PublishGuardrailVerdict(
            allowed=allowed,
            pressure=pressure,
            reason=reason,
            max_rate_per_hour=effective_cap,
        )

    def snapshot(self) -> dict[str, object]:
        state = self.repository.get_traffic_state()
        return {
            "pressure": state.get("pressure_level", TrafficPressure.PUBLIC_TRAFFIC_SAFE.value),
            "publishes_hour": len(self._publish_timestamps),
            "global_freeze": self.global_freeze,
            "languages": dict(self._lang_counts),
        }

    def summary_text(self) -> str:
        snap = self.snapshot()
        emoji = {
            TrafficPressure.PUBLIC_TRAFFIC_SAFE.value: "🟢",
            TrafficPressure.TRAFFIC_PRESSURE_HIGH.value: "🟡",
            TrafficPressure.TRAFFIC_PRESSURE_CRITICAL.value: "🔴",
        }.get(str(snap["pressure"]), "⚪")
        lines = [
            f"<b>{emoji} Traffic guardrails</b>",
            f"Level: <code>{snap['pressure']}</code>",
            f"Publishes/h: {snap['publishes_hour']} · Freeze: {'yes' if snap['global_freeze'] else 'no'}",
        ]
        return "\n".join(lines)
