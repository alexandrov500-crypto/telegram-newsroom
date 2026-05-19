from __future__ import annotations

import os
from dataclasses import dataclass

from bot.reliability.types import PublishMode


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
class ReliabilitySettings:
    enabled: bool = True
    burnin_mode: bool = False
    probe_interval_sec: float = 30.0
    recovery_max_attempts: int = 5
    recovery_backoff_base_sec: float = 30.0
    recovery_backoff_max_sec: float = 900.0
    publish_stability_sec: float = 3600.0
    publish_max_fatal_incidents: int = 0
    publish_max_queue_depth: int = 400
    publish_max_cognition_latency_ms: float = 120_000.0
    publish_max_telegram_failure_rate: float = 0.15
    limited_production_cap_per_hour: int = 12
    daily_report_interval_sec: float = 86_400.0
    error_window_sec: float = 3600.0

    @classmethod
    def from_env(cls) -> ReliabilitySettings:
        return cls(
            enabled=_env_bool("RELIABILITY_LAYER_ENABLED", "true"),
            burnin_mode=_env_bool("RELIABILITY_BURNIN_MODE", "false"),
            probe_interval_sec=_env_float("RELIABILITY_PROBE_INTERVAL_SEC", 30.0),
            recovery_max_attempts=_env_int("RELIABILITY_RECOVERY_MAX_ATTEMPTS", 5),
            recovery_backoff_base_sec=_env_float("RELIABILITY_RECOVERY_BACKOFF_BASE_SEC", 30.0),
            recovery_backoff_max_sec=_env_float("RELIABILITY_RECOVERY_BACKOFF_MAX_SEC", 900.0),
            publish_stability_sec=_env_float("PUBLISH_STABILITY_SEC", 3600.0),
            publish_max_fatal_incidents=_env_int("PUBLISH_MAX_FATAL_INCIDENTS", 0),
            publish_max_queue_depth=_env_int("PUBLISH_MAX_QUEUE_DEPTH", 400),
            publish_max_cognition_latency_ms=_env_float(
                "PUBLISH_MAX_COGNITION_LATENCY_MS", 120_000.0,
            ),
            publish_max_telegram_failure_rate=_env_float(
                "PUBLISH_MAX_TELEGRAM_FAILURE_RATE", 0.15,
            ),
            limited_production_cap_per_hour=_env_int(
                "LIMITED_PRODUCTION_CAP_PER_HOUR", 12,
            ),
            daily_report_interval_sec=_env_float(
                "RELIABILITY_DAILY_REPORT_INTERVAL_SEC", 86_400.0,
            ),
            error_window_sec=_env_float("RELIABILITY_ERROR_WINDOW_SEC", 3600.0),
        )

    def resolve_publish_mode(self) -> PublishMode:
        raw = os.getenv("RELIABILITY_PUBLISH_MODE", "").strip().upper()
        if raw == "FULL_PRODUCTION":
            return PublishMode.FULL_PRODUCTION
        if raw == "LIMITED_PRODUCTION":
            return PublishMode.LIMITED_PRODUCTION
        if raw == "DRY_RUN" or _env_bool("DRY_RUN", "false"):
            return PublishMode.DRY_RUN
        if _env_bool("SHADOW_PUBLISH_ONLY", "false") or _env_bool("STAGING_MODE", "false"):
            return PublishMode.SHADOW
        return PublishMode.SHADOW
