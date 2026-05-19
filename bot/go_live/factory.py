from __future__ import annotations

from pathlib import Path

from bot.go_live.coordinator import GoLiveCoordinator
from bot.go_live.first_publication import FirstPublicationWorkflow
from bot.go_live.repository import GoLiveRepository
from bot.go_live.settings import GoLiveSettings


def build_go_live_stack(db_path: Path) -> GoLiveCoordinator:
    settings = GoLiveSettings.from_env()
    repo = GoLiveRepository(db_path)
    return GoLiveCoordinator(
        settings=settings,
        repository=repo,
        first_publication=FirstPublicationWorkflow(repo),
    )
