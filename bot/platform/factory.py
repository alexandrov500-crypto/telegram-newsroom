from __future__ import annotations

from pathlib import Path

from bot.platform.cognition.agents import MultiAgentCognitionOrchestrator
from bot.platform.coordinator import PlatformCoordinator
from bot.platform.gateway.api import InternalApiGateway
from bot.platform.governance.maturity import PlatformGovernance
from bot.platform.graph.store import OperationalKnowledgeGraph
from bot.platform.idp.inventory import InternalDeveloperPlatform
from bot.platform.observability.hub import PlatformObservabilityHub
from bot.platform.plugins.registry import PluginRegistry
from bot.platform.policy.engine import PolicyEngine
from bot.platform.repository import PlatformRepository
from bot.platform.settings import PlatformSettings
from bot.platform.workflow.runtime import PlatformWorkflowRuntime


def build_platform_stack(db_path: Path) -> PlatformCoordinator:
    settings = PlatformSettings.from_env()
    repo = PlatformRepository(db_path)
    return PlatformCoordinator(
        settings=settings,
        repository=repo,
        plugins=PluginRegistry(repo),
        idp=InternalDeveloperPlatform(repo),
        workflows=PlatformWorkflowRuntime(repo),
        graph=OperationalKnowledgeGraph(repo),
        cognition=MultiAgentCognitionOrchestrator(),
        policies=PolicyEngine(repo),
        observability=PlatformObservabilityHub(),
        gateway=InternalApiGateway(repo),
        governance=PlatformGovernance(),
    )
