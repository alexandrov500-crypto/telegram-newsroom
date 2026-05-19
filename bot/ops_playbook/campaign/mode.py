from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository

logger = logging.getLogger(__name__)

_CAMPAIGN_DEFAULTS: dict[str, dict[str, Any]] = {
    "breaking": {
        "pacing_multiplier": 0.6,
        "cognition_priority_boost": 1.3,
        "duplicate_threshold": 0.85,
        "trust_threshold": 0.8,
        "require_approval": True,
        "multilingual_amp": True,
    },
    "election": {
        "pacing_multiplier": 0.5,
        "cognition_priority_boost": 1.2,
        "duplicate_threshold": 0.88,
        "trust_threshold": 0.85,
        "require_approval": True,
        "multilingual_amp": True,
    },
    "sports": {
        "pacing_multiplier": 0.7,
        "cognition_priority_boost": 1.15,
        "duplicate_threshold": 0.82,
        "trust_threshold": 0.75,
        "require_approval": True,
        "multilingual_amp": False,
    },
    "default": {
        "pacing_multiplier": 0.65,
        "cognition_priority_boost": 1.25,
        "duplicate_threshold": 0.84,
        "trust_threshold": 0.78,
        "require_approval": True,
        "multilingual_amp": True,
    },
}


@dataclass
class CampaignModeEngine:
    """High-attention event overrides — in-memory + DB, no rollout mutation."""

    repository: OpsPlaybookRepository

    def start(self, campaign_type: str = "breaking") -> str:
        cfg = dict(_CAMPAIGN_DEFAULTS.get(campaign_type, _CAMPAIGN_DEFAULTS["default"]))
        cfg["surge_throttle"] = True
        self.repository.set_campaign(active=True, campaign_type=campaign_type, config=cfg)
        logger.info("event=campaign_mode_start type=%s", campaign_type)
        return (
            f"<b>Campaign mode ON</b> · <code>{campaign_type}</code>\n"
            f"Pacing ×{cfg['pacing_multiplier']} · trust ≥{cfg['trust_threshold']}\n"
            f"Approval escalation: {'yes' if cfg['require_approval'] else 'no'}"
        )

    def stop(self) -> str:
        self.repository.set_campaign(active=False, campaign_type=None, config={})
        logger.info("event=campaign_mode_stop")
        return "Campaign mode OFF — normal pacing restored."

    def status(self) -> str:
        row = self.repository.get_campaign()
        if not row or not row.get("active"):
            return "Campaign mode: <b>inactive</b>"
        cfg = row.get("config") or {}
        return (
            f"<b>Campaign mode</b> · <code>{row.get('campaign_type')}</code>\n"
            f"Since: {row.get('started_at', '?')}\n"
            f"Pacing ×{cfg.get('pacing_multiplier', 1)} · "
            f"dup≥{cfg.get('duplicate_threshold', 0.8)} · "
            f"trust≥{cfg.get('trust_threshold', 0.75)}"
        )

    def active_config(self) -> dict[str, Any] | None:
        row = self.repository.get_campaign()
        if row and row.get("active"):
            return row.get("config")
        return None
