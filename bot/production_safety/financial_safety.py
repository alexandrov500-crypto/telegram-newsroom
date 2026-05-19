from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.types import CostMode, FinancialSnapshot

logger = logging.getLogger(__name__)


@dataclass
class FinancialSafetyController:
    """Hard AI spend caps with degraded cognition modes."""

    settings: ProductionSafetySettings
    _hourly_samples: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=48))
    _story_spend: dict[int, float] = field(default_factory=dict)

    def record_spend(self, usd: float, *, story_id: int | None = None) -> None:
        if usd <= 0:
            return
        now = time.monotonic()
        self._hourly_samples.append((now, usd))
        if story_id is not None:
            self._story_spend[story_id] = self._story_spend.get(story_id, 0.0) + usd

    def _hourly_total(self) -> float:
        cutoff = time.monotonic() - 3600.0
        return sum(u for t, u in self._hourly_samples if t >= cutoff)

    def _daily_total(self, obs_repo: Any | None) -> float:
        if obs_repo is not None:
            try:
                from datetime import datetime, timezone

                day = datetime.now(timezone.utc).date().isoformat()
                row = obs_repo.get_daily(day)
                if row:
                    return float(row.get("cost_usd", 0))
            except Exception:
                pass
        cutoff = time.monotonic() - 86400.0
        return sum(u for t, u in self._hourly_samples if t >= cutoff)

    def current_mode(self, *, obs_repo: Any | None = None) -> CostMode:
        daily = self._daily_total(obs_repo)
        ratio = daily / max(self.settings.daily_budget_usd, 0.01)
        if ratio >= self.settings.emergency_cost_threshold:
            return CostMode.EMERGENCY_LOW_COST
        if ratio >= self.settings.cost_saving_threshold:
            return CostMode.COST_SAVING
        hourly = self._hourly_total()
        if hourly >= self.settings.hourly_budget_usd:
            return CostMode.COST_SAVING
        return CostMode.NORMAL

    def allow_story_spend(self, story_id: int, incremental_usd: float) -> bool:
        current = self._story_spend.get(story_id, 0.0)
        return (current + incremental_usd) <= self.settings.per_story_token_ceiling_usd

    def snapshot(self, *, obs_repo: Any | None = None, stories_today: int = 1) -> FinancialSnapshot:
        daily = self._daily_total(obs_repo)
        hourly = self._hourly_total()
        cap = self.settings.daily_budget_usd
        projected = daily + hourly * max(1, 24 - int(time.monotonic() % 86400 // 3600))
        cps = daily / max(stories_today, 1)
        mode = self.current_mode(obs_repo=obs_repo)
        anomaly = daily > cap * 1.1 or hourly > self.settings.hourly_budget_usd * 1.5
        if anomaly:
            logger.warning(
                "event=cost_anomaly daily=%.2f hourly=%.2f cap=%.2f",
                daily,
                hourly,
                cap,
            )
        return FinancialSnapshot(
            mode=mode,
            hourly_spend_usd=round(hourly, 4),
            daily_spend_usd=round(daily, 4),
            daily_cap_usd=cap,
            projected_daily_usd=round(projected, 4),
            cost_per_story_usd=round(cps, 4),
            anomaly=anomaly,
        )

    def fallback_model_hint(self) -> str | None:
        mode = self.current_mode()
        if mode == CostMode.EMERGENCY_LOW_COST:
            return "gpt-4.1-nano"
        if mode == CostMode.COST_SAVING:
            return "gpt-4.1-mini"
        return None
