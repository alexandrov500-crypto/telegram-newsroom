from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from typing import Any

from bot.operations.repository import OperationsRepository
from bot.operations.types import BURNIN_PROFILES, BurnInProfile

logger = logging.getLogger(__name__)


@dataclass
class BurnInBaseline:
    profile: str
    samples: int
    health_mean: float
    health_min: float
    backlog_mean: float
    epistemic_stability_mean: float
    regressions: list[str]


class BurnInRunner:
    """Long-running operational validation with stability baselines."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository
        self._active_run: str | None = None
        self._sample_count = 0

    def start(self, profile_name: str = "24h") -> str:
        profile = BURNIN_PROFILES.get(profile_name, BURNIN_PROFILES["24h"])
        self._active_run = self._repo.start_burnin(profile.name)
        self._sample_count = 0
        logger.info("event=burnin_started run_id=%s profile=%s", self._active_run, profile.name)
        return self._active_run

    def record_sample(self, metrics: dict[str, Any]) -> None:
        if not self._active_run:
            return
        self._repo.record_burnin_sample(self._active_run, metrics)
        self._sample_count += 1
        try:
            from bot.observability.metrics import set_burnin_health

            set_burnin_health(float(metrics.get("health_score", 1.0)))
        except Exception:
            pass

    def analyze_baseline(self, run_id: str) -> BurnInBaseline:
        rows = self._repo.burnin_samples(run_id)
        if not rows:
            return BurnInBaseline("unknown", 0, 0.0, 0.0, 0.0, 0.0, ["no samples"])

        healths: list[float] = []
        backlogs: list[float] = []
        epistemic: list[float] = []
        regressions: list[str] = []
        prev_health = None

        for row in reversed(rows):
            m = json.loads(row["metrics_json"])
            h = float(m.get("health_score", 1.0))
            healths.append(h)
            backlogs.append(float(m.get("queue_backlog", 0)))
            epistemic.append(float(m.get("epistemic_stability", 1.0)))
            if prev_health is not None and prev_health - h > 0.2:
                regressions.append(f"health_drop at {row['sample_at']}: {prev_health:.2f}->{h:.2f}")
            prev_health = h

        if healths and statistics.mean(healths) < 0.6:
            regressions.append("mean_health_below_baseline")
        if epistemic and statistics.mean(epistemic) < 0.65:
            regressions.append("epistemic_stability_regression")

        return BurnInBaseline(
            profile=run_id,
            samples=len(rows),
            health_mean=round(statistics.mean(healths), 4) if healths else 0.0,
            health_min=round(min(healths), 4) if healths else 0.0,
            backlog_mean=round(statistics.mean(backlogs), 2) if backlogs else 0.0,
            epistemic_stability_mean=round(statistics.mean(epistemic), 4) if epistemic else 0.0,
            regressions=regressions,
        )

    def complete(self, *, health_score: float, summary: dict) -> BurnInBaseline | None:
        if not self._active_run:
            return None
        self._repo.complete_burnin(self._active_run, health_score=health_score, summary=summary)
        baseline = self.analyze_baseline(self._active_run)
        run_id = self._active_run
        self._active_run = None
        logger.info("event=burnin_completed run_id=%s health=%.2f", run_id, health_score)
        return baseline

    @property
    def active_run_id(self) -> str | None:
        return self._active_run
