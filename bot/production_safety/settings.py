from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class ProductionSafetySettings:
    enabled: bool = True
    daily_budget_usd: float = 50.0
    hourly_budget_usd: float = 8.0
    per_story_token_ceiling_usd: float = 0.35
    cost_saving_threshold: float = 0.75
    emergency_cost_threshold: float = 0.95
    min_publish_confidence: float = 0.62
    min_source_diversity: int = 1
    max_queue_depth: int = 600
    max_async_tasks: int = 500
    memory_rss_warn_mb: float = 2048.0
    telegram_min_interval_sec: float = 0.35
    floodwait_backoff_multiplier: float = 1.5
    rollout_stage: str = "INTERNAL_SHADOW"
    channel_whitelist: frozenset[int] = frozenset()
    limited_publishes_per_hour: int = 6
    operator_silent_hours: float = 4.0
    auto_rollback_on_fatal: bool = True

    @classmethod
    def from_env(cls) -> ProductionSafetySettings:
        raw_whitelist = os.getenv("PRODUCTION_CHANNEL_WHITELIST", "").strip()
        whitelist: set[int] = set()
        for part in raw_whitelist.split(","):
            token = part.strip()
            if token:
                try:
                    whitelist.add(int(token))
                except ValueError:
                    pass
        return cls(
            enabled=_env_bool("PRODUCTION_SAFETY_ENABLED", "true"),
            daily_budget_usd=_env_float("PRODUCTION_DAILY_BUDGET_USD", 50.0),
            hourly_budget_usd=_env_float("PRODUCTION_HOURLY_BUDGET_USD", 8.0),
            per_story_token_ceiling_usd=_env_float("PRODUCTION_PER_STORY_BUDGET_USD", 0.35),
            cost_saving_threshold=_env_float("PRODUCTION_COST_SAVING_RATIO", 0.75),
            emergency_cost_threshold=_env_float("PRODUCTION_COST_EMERGENCY_RATIO", 0.95),
            min_publish_confidence=_env_float("PRODUCTION_MIN_PUBLISH_CONFIDENCE", 0.62),
            min_source_diversity=_env_int("PRODUCTION_MIN_SOURCE_DIVERSITY", 1),
            max_queue_depth=_env_int("PRODUCTION_MAX_QUEUE_DEPTH", 600),
            max_async_tasks=_env_int("PRODUCTION_MAX_ASYNC_TASKS", 500),
            memory_rss_warn_mb=_env_float("PRODUCTION_MEMORY_WARN_MB", 2048.0),
            telegram_min_interval_sec=_env_float("PRODUCTION_TELEGRAM_MIN_INTERVAL_SEC", 0.35),
            floodwait_backoff_multiplier=_env_float("PRODUCTION_FLOODWAIT_MULTIPLIER", 1.5),
            rollout_stage=os.getenv("PRODUCTION_ROLLOUT_STAGE", "INTERNAL_SHADOW").strip().upper(),
            channel_whitelist=frozenset(whitelist),
            limited_publishes_per_hour=_env_int("PRODUCTION_LIMITED_PUBLISHES_PER_HOUR", 6),
            operator_silent_hours=_env_float("PRODUCTION_OPERATOR_SILENT_HOURS", 4.0),
            auto_rollback_on_fatal=_env_bool("PRODUCTION_AUTO_ROLLBACK_FATAL", "true"),
        )
