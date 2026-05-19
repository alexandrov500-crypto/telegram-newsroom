from __future__ import annotations

from pathlib import Path

from bot.ops_playbook.auditor.compliance import OperationsAuditor
from bot.ops_playbook.campaign.mode import CampaignModeEngine
from bot.ops_playbook.coordinator import OpsPlaybookCoordinator
from bot.ops_playbook.executive.briefings import ExecutiveIncidentBriefing
from bot.ops_playbook.launch_period.protections import LaunchPeriodProtections
from bot.ops_playbook.reputation.analytics import ChannelReputationAnalytics
from bot.ops_playbook.repository import OpsPlaybookRepository
from bot.ops_playbook.rhythm.scheduler import OperationsRhythmScheduler
from bot.ops_playbook.settings import OpsPlaybookSettings
from bot.ops_playbook.shift.handoff import ShiftHandoffEngine
from bot.ops_playbook.training.simulator import OperatorTrainingSimulator
from bot.ops_playbook.war_room.mode import WarRoomMode


def build_ops_playbook_stack(db_path: Path) -> OpsPlaybookCoordinator:
    settings = OpsPlaybookSettings.from_env()
    repo = OpsPlaybookRepository(db_path)
    return OpsPlaybookCoordinator(
        settings=settings,
        repository=repo,
        shift=ShiftHandoffEngine(repo),
        war_room=WarRoomMode(repo),
        campaign=CampaignModeEngine(repo),
        rhythm=OperationsRhythmScheduler(repo),
        training=OperatorTrainingSimulator(repo),
        reputation=ChannelReputationAnalytics(repo),
        executive=ExecutiveIncidentBriefing(),
        auditor=OperationsAuditor(repo),
        launch_period=LaunchPeriodProtections(repo, settings),
    )
