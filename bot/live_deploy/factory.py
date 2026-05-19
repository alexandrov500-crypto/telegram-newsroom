from __future__ import annotations

from pathlib import Path

from bot.live_deploy.coordinator import LiveDeployCoordinator
from bot.live_deploy.executive_report import ExecutiveGoLiveReport
from bot.live_deploy.first_72h import First72HMode
from bot.live_deploy.publication_guard import LivePublicationGuard
from bot.live_deploy.repository import LiveDeployRepository
from bot.live_deploy.settings import LiveDeploySettings


def build_live_deploy_stack(db_path: Path) -> LiveDeployCoordinator:
    settings = LiveDeploySettings.from_env()
    repo = LiveDeployRepository(db_path)
    first_72h = First72HMode(settings, repo)
    return LiveDeployCoordinator(
        settings=settings,
        repository=repo,
        first_72h=first_72h,
        publication_guard=LivePublicationGuard(repo, first_72h),
        executive=ExecutiveGoLiveReport(repo),
    )
