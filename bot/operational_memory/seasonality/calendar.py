from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.operational_memory.repository import OperationalMemoryRepository


class SeasonalityCalendar:
    """Time-aware operational baselines."""

    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository

    def bucket_key(self, now: datetime | None = None) -> str:
        dt = now or datetime.now(timezone.utc)
        wd = "weekend" if dt.weekday() >= 5 else "weekday"
        hour = dt.hour
        band = "night" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        return f"{wd}:{band}"

    def update(self, signals: dict[str, Any]) -> dict[str, Any]:
        key = self.bucket_key()
        existing = self.repository.get_seasonality(key) or {
            "samples": 0,
            "avg_queue": 0.0,
            "avg_risk": 0.0,
            "avg_survivability": 0.8,
        }
        n = int(existing.get("samples", 0)) + 1
        q = float(signals.get("queue_depth", 0))
        risk = float(signals.get("stabilization_risk", 0.3))
        surv = float(signals.get("survivability_score", 0.8))
        profile = {
            "bucket": key,
            "samples": n,
            "avg_queue": (existing["avg_queue"] * (n - 1) + q) / n,
            "avg_risk": (existing["avg_risk"] * (n - 1) + risk) / n,
            "avg_survivability": (existing["avg_survivability"] * (n - 1) + surv) / n,
            "campaign_spike": bool(signals.get("campaign_active")),
            "geopolitical_burst": bool(signals.get("breaking_news_mode")),
        }
        self.repository.upsert_seasonality(key, profile)
        return profile

    def contextual_baseline(self, signals: dict[str, Any]) -> dict[str, float]:
        key = self.bucket_key()
        profile = self.repository.get_seasonality(key)
        if not profile:
            return {
                "queue": float(signals.get("queue_depth", 0)),
                "risk": float(signals.get("stabilization_risk", 0.3)),
            }
        return {
            "queue": profile.get("avg_queue", 0.0),
            "risk": profile.get("avg_risk", 0.3),
            "survivability": profile.get("avg_survivability", 0.8),
        }

    def seasonality_state_html(self) -> str:
        key = self.bucket_key()
        profile = self.repository.get_seasonality(key)
        if not profile:
            return f"<b>Seasonality</b>\nBucket <code>{key}</code> — warming up."
        return (
            f"<b>Seasonality</b> <code>{key}</code>\n"
            f"Samples: {profile.get('samples', 0)}\n"
            f"Avg queue: {profile.get('avg_queue', 0):.0f}\n"
            f"Avg risk: {profile.get('avg_risk', 0):.0%}\n"
            f"Survivability: {profile.get('avg_survivability', 0):.0%}"
        )
