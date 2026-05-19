from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PostGaSettings:
    enabled: bool = False
    calibration: bool = True
    quality_learning: bool = True
    autonomy_stabilization: bool = True
    operator_load_reduction: bool = True
    analytics: bool = True
    risk_prediction: bool = True
    self_optimization: bool = True
    governance_evolution: bool = True
    probe_interval_sec: float = 60.0
    optimization_auto_threshold: float = 0.05

    @classmethod
    def from_env(cls) -> PostGaSettings:
        enabled = os.getenv("POST_GA_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("APP_ENV", "").lower() == "production"
        return cls(
            enabled=enabled,
            calibration=os.getenv("POST_GA_CALIBRATION", "true").lower()
            not in ("0", "false", "no"),
            quality_learning=os.getenv("POST_GA_QUALITY_LEARNING", "true").lower()
            not in ("0", "false", "no"),
            autonomy_stabilization=os.getenv("POST_GA_AUTONOMY", "true").lower()
            not in ("0", "false", "no"),
            operator_load_reduction=os.getenv("POST_GA_OPERATOR_LOAD", "true").lower()
            not in ("0", "false", "no"),
            analytics=os.getenv("POST_GA_ANALYTICS", "true").lower()
            not in ("0", "false", "no"),
            risk_prediction=os.getenv("POST_GA_RISK", "true").lower()
            not in ("0", "false", "no"),
            self_optimization=os.getenv("POST_GA_OPTIMIZATION", "true").lower()
            not in ("0", "false", "no"),
            governance_evolution=os.getenv("POST_GA_GOVERNANCE", "true").lower()
            not in ("0", "false", "no"),
            probe_interval_sec=float(os.getenv("POST_GA_PROBE_INTERVAL_SEC", "60")),
            optimization_auto_threshold=float(os.getenv("POST_GA_OPT_THRESHOLD", "0.05")),
        )
