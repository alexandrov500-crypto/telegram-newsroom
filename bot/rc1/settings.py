from __future__ import annotations

import os
from dataclasses import dataclass


RC1_BUILD_ID = "rc1-2026.05.17"


@dataclass(frozen=True)
class Rc1Settings:
    enabled: bool = False
    lockdown_mode: bool = False
    profiling_enabled: bool = True
    baselines_enabled: bool = True
    activation_enabled: bool = True
    live_validation_enabled: bool = True
    probe_interval_sec: float = 60.0

    @classmethod
    def from_env(cls) -> Rc1Settings:
        enabled = os.getenv("RC1_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("APP_ENV", "").lower() in ("staging", "production")
        lockdown = os.getenv("RC1_LOCKDOWN_MODE", "").lower() in ("1", "true", "yes")
        if not lockdown and os.getenv("APP_ENV", "").lower() == "production":
            lockdown = os.getenv("RC1_LOCKDOWN_MODE", "true").lower() not in (
                "0",
                "false",
                "no",
            )
        return cls(
            enabled=enabled,
            lockdown_mode=lockdown,
            profiling_enabled=os.getenv("RC1_PROFILING", "true").lower()
            not in ("0", "false", "no"),
            baselines_enabled=os.getenv("RC1_BASELINES", "true").lower()
            not in ("0", "false", "no"),
            activation_enabled=os.getenv("RC1_ACTIVATION", "true").lower()
            not in ("0", "false", "no"),
            live_validation_enabled=os.getenv("RC1_LIVE_VALIDATION", "true").lower()
            not in ("0", "false", "no"),
            probe_interval_sec=float(os.getenv("RC1_PROBE_INTERVAL_SEC", "60")),
        )
