from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GaOpsSettings:
    enabled: bool = False
    traffic_guardrails: bool = True
    quality_validation: bool = True
    feedback_loop: bool = True
    retention_enabled: bool = True
    scaling_forecast: bool = True
    rollback_hardening: bool = True
    ga_readiness_min_score: float = 0.88
    max_publishes_per_hour: int = 40
    surge_queue_threshold: int = 300
    probe_interval_sec: float = 60.0

    @classmethod
    def from_env(cls) -> GaOpsSettings:
        enabled = os.getenv("GA_OPS_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("APP_ENV", "").lower() in ("staging", "production")
        return cls(
            enabled=enabled,
            traffic_guardrails=os.getenv("GA_TRAFFIC_GUARDRAILS", "true").lower()
            not in ("0", "false", "no"),
            quality_validation=os.getenv("GA_QUALITY_VALIDATION", "true").lower()
            not in ("0", "false", "no"),
            feedback_loop=os.getenv("GA_FEEDBACK_LOOP", "true").lower()
            not in ("0", "false", "no"),
            retention_enabled=os.getenv("GA_RETENTION", "true").lower()
            not in ("0", "false", "no"),
            scaling_forecast=os.getenv("GA_SCALING", "true").lower()
            not in ("0", "false", "no"),
            rollback_hardening=os.getenv("GA_ROLLBACK_HARDENING", "true").lower()
            not in ("0", "false", "no"),
            ga_readiness_min_score=float(os.getenv("GA_READINESS_MIN_SCORE", "0.88")),
            max_publishes_per_hour=int(os.getenv("GA_MAX_PUBLISHES_PER_HOUR", "40")),
            surge_queue_threshold=int(os.getenv("GA_SURGE_QUEUE_THRESHOLD", "300")),
            probe_interval_sec=float(os.getenv("GA_PROBE_INTERVAL_SEC", "60")),
        )
