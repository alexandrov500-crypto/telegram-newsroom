from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.platform.cognition.agents import MultiAgentCognitionOrchestrator
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

logger = logging.getLogger(__name__)


@dataclass
class PlatformCoordinator:
    settings: PlatformSettings
    repository: PlatformRepository
    plugins: PluginRegistry
    idp: InternalDeveloperPlatform
    workflows: PlatformWorkflowRuntime
    graph: OperationalKnowledgeGraph
    cognition: MultiAgentCognitionOrchestrator
    policies: PolicyEngine
    observability: PlatformObservabilityHub
    gateway: InternalApiGateway
    governance: PlatformGovernance
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _last_snapshot: dict[str, Any] | None = None
    _tick: int = 0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        if self.settings.plugins:
            self.plugins.bootstrap()
        if self.settings.workflows:
            self.workflows.register_builtin_workflows()
        self.idp.bootstrap_defaults()
        self.idp.build_inventory()
        if self.settings.policy_engine:
            self.policies.bootstrap_defaults()
        self.graph.link("risk", "queue", "channel", "default", "monitors")
        logger.info("event=platform_installed")

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = signals or (self._signals_fn() if self._signals_fn else {})

        if self.settings.graph and self._tick % 12 == 0:
            for issue in sig.get("failure_issues", [])[:2]:
                key = str(issue.get("id", "unknown"))
                self.graph.risk_incident(f"ops:{key}", key)
                self.graph.incident_story(key, int(issue.get("story_id", 0) or 0))

        plugin_list = self.plugins.list_live()
        drift = len(self.policies.drift_check()) if self.settings.policy_engine else 0
        trust_vals = [float(p.get("trust_score", 0.5)) for p in plugin_list]
        trust_avg = sum(trust_vals) / len(trust_vals) if trust_vals else 0.9
        quarantined = sum(1 for p in plugin_list if p.get("health_status") != "healthy")

        risk_score = self.governance.ecosystem_risk_score(
            plugin_trust_avg=trust_avg,
            policy_drift_count=drift,
            quarantined_plugins=quarantined,
            open_incidents=len(sig.get("failure_issues", [])),
        )

        snap = self.observability.snapshot(
            plugins=plugin_list,
            workflows="ok",
            policies=len(self.repository.active_policies()),
            graph_edges=self.repository.graph_edge_count(),
            agent_debates=len(self.cognition._debates),
        )
        snap["ecosystem_risk"] = risk_score
        self._last_snapshot = snap

        return {
            "plugins": len(plugin_list),
            "graph_edges": snap["graph_edges"],
            "ecosystem_risk": risk_score,
            "policies": snap["policies_count"],
        }

    def platform_health_text(self) -> str:
        snap = self._last_snapshot or {}
        return self.observability.platform_health_text(snap)

    def topology_snapshot_text(self) -> str:
        snap = self._last_snapshot or {}
        return self.observability.topology_text(snap)

    def ecosystem_risk_text(self) -> str:
        snap = self._last_snapshot or {}
        plugin_list = self.plugins.list_live()
        trust_vals = [float(p.get("trust_score", 0.5)) for p in plugin_list]
        trust_avg = sum(trust_vals) / len(trust_vals) if trust_vals else 0.9
        return self.governance.ecosystem_risk_text(
            float(snap.get("ecosystem_risk", 0)),
            {
                "trust_avg": trust_avg,
                "drift": len(self.policies.drift_check()),
                "quarantined": sum(
                    1 for p in plugin_list if p.get("health_status") != "healthy"
                ),
            },
        )

    def governance_audit_text(self) -> str:
        return self.governance.governance_audit_text(
            self.plugins.list_live(),
            len(self.repository.active_policies()),
        )
