from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LiveDeploySettings:
    enabled: bool = True
    first_72h_mode: bool = False
    first_72h_hours: int = 72
    min_quality_public: float = 0.72
    min_trust_public: float = 0.78
    min_confidence_public: float = 0.82
    mandatory_operator_approval: bool = True
    elevated_telemetry: bool = True

    @classmethod
    def from_env(cls) -> LiveDeploySettings:
        enabled = os.getenv("LIVE_DEPLOY_ENABLED", "true").lower() not in ("0", "false", "no")
        first_72h = os.getenv("FIRST_72H_MODE", "").lower() in ("1", "true", "yes")
        if not first_72h:
            first_72h = os.getenv("OPS_PLAYBOOK_ENABLED", "").lower() in ("1", "true", "yes")
        return cls(
            enabled=enabled,
            first_72h_mode=first_72h,
            first_72h_hours=int(os.getenv("FIRST_72H_HOURS", "72")),
            min_quality_public=float(os.getenv("LIVE_MIN_QUALITY", "0.72")),
            min_trust_public=float(os.getenv("LIVE_MIN_TRUST", "0.78")),
            min_confidence_public=float(os.getenv("LIVE_MIN_CONFIDENCE", "0.82")),
            mandatory_operator_approval=os.getenv("LIVE_MANDATORY_APPROVAL", "true").lower()
            not in ("0", "false", "no"),
            elevated_telemetry=os.getenv("LIVE_ELEVATED_TELEMETRY", "true").lower()
            not in ("0", "false", "no"),
        )
