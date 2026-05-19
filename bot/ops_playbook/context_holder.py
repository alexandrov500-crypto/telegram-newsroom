from __future__ import annotations

from bot.ops_playbook.coordinator import OpsPlaybookCoordinator

_playbook: OpsPlaybookCoordinator | None = None


def install_ops_playbook(coordinator: OpsPlaybookCoordinator | None) -> None:
    global _playbook
    _playbook = coordinator


def get_ops_playbook() -> OpsPlaybookCoordinator | None:
    return _playbook
