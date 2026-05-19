from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class OpsPlaybookSettings:
    enabled: bool = False
    shift_handoff: bool = True
    war_room: bool = True
    campaign_mode: bool = True
    daily_rhythm: bool = True
    training_mode: bool = True
    reputation: bool = True
    auditor: bool = True
    launch_period_days: int = 30
    launch_period_elevated_sensitivity: bool = True

    @classmethod
    def from_env(cls) -> OpsPlaybookSettings:
        enabled = os.getenv("OPS_PLAYBOOK_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("PLATFORM_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("OPS_EVOLUTION_ENABLED", "").lower() in ("1", "true", "yes")
        return cls(
            enabled=enabled,
            shift_handoff=os.getenv("OPS_PLAYBOOK_SHIFT", "true").lower()
            not in ("0", "false", "no"),
            war_room=os.getenv("OPS_PLAYBOOK_WAR_ROOM", "true").lower()
            not in ("0", "false", "no"),
            campaign_mode=os.getenv("OPS_PLAYBOOK_CAMPAIGN", "true").lower()
            not in ("0", "false", "no"),
            daily_rhythm=os.getenv("OPS_PLAYBOOK_RHYTHM", "true").lower()
            not in ("0", "false", "no"),
            training_mode=os.getenv("OPS_PLAYBOOK_TRAINING", "true").lower()
            not in ("0", "false", "no"),
            reputation=os.getenv("OPS_PLAYBOOK_REPUTATION", "true").lower()
            not in ("0", "false", "no"),
            auditor=os.getenv("OPS_PLAYBOOK_AUDITOR", "true").lower()
            not in ("0", "false", "no"),
            launch_period_days=int(os.getenv("OPS_LAUNCH_PERIOD_DAYS", "30")),
            launch_period_elevated_sensitivity=os.getenv(
                "OPS_LAUNCH_ELEVATED",
                "true",
            ).lower()
            not in ("0", "false", "no"),
        )

    @staticmethod
    def default_production_start() -> str:
        raw = os.getenv("OPS_PRODUCTION_START_AT", "")
        if raw:
            return raw
        return datetime.now(timezone.utc).isoformat()
