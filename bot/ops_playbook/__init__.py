"""Production operations playbook automation."""

from bot.ops_playbook.context_holder import get_ops_playbook, install_ops_playbook
from bot.ops_playbook.coordinator import OpsPlaybookCoordinator
from bot.ops_playbook.factory import build_ops_playbook_stack

__all__ = [
    "OpsPlaybookCoordinator",
    "build_ops_playbook_stack",
    "get_ops_playbook",
    "install_ops_playbook",
]
