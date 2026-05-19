from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Week1Settings:
    enabled: bool = False
    alert_dedupe_sec: int = 900
    actionable_only: bool = True
    baseline_auto_capture: bool = True
    week_days: int = 7

    @classmethod
    def from_env(cls) -> Week1Settings:
        enabled = os.getenv("WEEK1_STABILIZATION_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("LIVE_DEPLOY_ENABLED", "").lower() in ("1", "true", "yes")
        return cls(
            enabled=enabled,
            alert_dedupe_sec=int(os.getenv("WEEK1_ALERT_DEDUPE_SEC", "900")),
            actionable_only=os.getenv("WEEK1_ACTIONABLE_ONLY", "true").lower()
            not in ("0", "false", "no"),
            baseline_auto_capture=os.getenv("WEEK1_BASELINE_CAPTURE", "true").lower()
            not in ("0", "false", "no"),
            week_days=int(os.getenv("WEEK1_DAYS", "7")),
        )
