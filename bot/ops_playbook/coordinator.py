from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.ops_playbook.auditor.compliance import OperationsAuditor
from bot.ops_playbook.campaign.mode import CampaignModeEngine
from bot.ops_playbook.executive.briefings import ExecutiveIncidentBriefing
from bot.ops_playbook.launch_period.protections import LaunchPeriodProtections
from bot.ops_playbook.reputation.analytics import ChannelReputationAnalytics
from bot.ops_playbook.repository import OpsPlaybookRepository
from bot.ops_playbook.rhythm.scheduler import OperationsRhythmScheduler
from bot.ops_playbook.settings import OpsPlaybookSettings
from bot.ops_playbook.shift.handoff import ShiftHandoffEngine
from bot.ops_playbook.training.simulator import OperatorTrainingSimulator
from bot.ops_playbook.war_room.mode import WarRoomMode

logger = logging.getLogger(__name__)


@dataclass
class OpsPlaybookCoordinator:
    settings: OpsPlaybookSettings
    repository: OpsPlaybookRepository
    shift: ShiftHandoffEngine
    war_room: WarRoomMode
    campaign: CampaignModeEngine
    rhythm: OperationsRhythmScheduler
    training: OperatorTrainingSimulator
    reputation: ChannelReputationAnalytics
    executive: ExecutiveIncidentBriefing
    auditor: OperationsAuditor
    launch_period: LaunchPeriodProtections
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _last_rhythm: dict[str, Any] | None = None

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        self.launch_period.ensure_initialized(
            OpsPlaybookSettings.default_production_start(),
        )
        logger.info("event=ops_playbook_installed")

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        sig = dict(signals or (self._signals_fn() if self._signals_fn else {}))
        if self.war_room.alert_freeze_active:
            sig["alert_freeze"] = True
        if self.campaign.active_config():
            sig["campaign_active"] = True
            sig.update(self.campaign.active_config() or {})

        launch_risk = self.launch_period.launch_risk_score(sig)
        sig["launch_risk"] = launch_risk
        sig["launch_protections"] = self.launch_period.active()

        rep = {}
        if self.settings.reputation:
            rep = self.reputation.ingest(sig)

        rhythm_out = {}
        if self.settings.daily_rhythm:
            rhythm_out = self.rhythm.tick(sig)
            if rhythm_out:
                self._last_rhythm = rhythm_out

        return {
            "launch_risk": launch_risk,
            "launch_protections": self.launch_period.active(),
            "reputation": rep.get("channel_reputation", 0),
            "war_room": bool(self.repository.active_war_room()),
            "campaign": bool(self.campaign.active_config()),
            "training": self.training.training_active,
        }

    def shift_handoff_text(self) -> str:
        sig = self._signals_fn() if self._signals_fn else {}
        report = self.shift.build_report(sig)
        shift = self.repository.get_shift() or {}
        owner = shift.get("owner_operator_id")
        return self.shift.handoff_html(report, owner=owner)
