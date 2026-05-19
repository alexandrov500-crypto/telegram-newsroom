from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.platform.repository import PlatformRepository


@dataclass
class ServiceDescriptor:
    name: str
    owner: str
    contracts: list[str] = field(default_factory=list)


@dataclass
class InternalDeveloperPlatform:
    """Service discovery, schema catalog, architecture inventory."""

    repository: PlatformRepository
    _services: dict[str, ServiceDescriptor] = field(default_factory=dict)
    _event_schemas: dict[str, str] = field(default_factory=dict)

    def register_service(self, name: str, *, owner: str, contracts: list[str]) -> None:
        self._services[name] = ServiceDescriptor(name=name, owner=owner, contracts=contracts)

    def register_event_schema(self, event_type: str, version: str = "1") -> None:
        self._event_schemas[event_type] = version

    def bootstrap_defaults(self) -> None:
        defaults = (
            ("event_bus", "platform", ["EventEnvelope", "LiveEventType"]),
            ("ga_ops", "editorial", ["PublishGuardrail", "QualityVerdict"]),
            ("post_ga", "operations", ["TrafficCalibrator", "RiskPredictor"]),
            ("ops_evolution", "platform", ["OperationalMemory", "MaturityModel"]),
            ("workflow_runtime", "platform", ["WorkflowRun", "Checkpoint"]),
            ("worker_mesh", "infra", ["WorkerRole", "Heartbeat"]),
        )
        for name, owner, contracts in defaults:
            self.register_service(name, owner=owner, contracts=contracts)
        for et in (
            "StoryIngested",
            "CognitionCompleted",
            "PublishDelivered",
            "IncidentCreated",
            "RolloutChanged",
        ):
            self.register_event_schema(et)

    def build_inventory(self) -> dict[str, Any]:
        inv = {
            "services": {
                k: {"owner": v.owner, "contracts": v.contracts}
                for k, v in self._services.items()
            },
            "event_schemas": dict(self._event_schemas),
            "dependencies": self._dependency_map(),
        }
        self.repository.save_inventory(inv)
        return inv

    def _dependency_map(self) -> dict[str, list[str]]:
        return {
            "main": ["event_bus", "ga_ops", "post_ga", "ops_evolution", "platform"],
            "publish_flow": ["ga_ops", "production_safety", "reliability"],
            "worker_mesh": ["event_bus", "redis"],
        }

    def inventory_text(self) -> str:
        inv = self.repository.get_inventory() or self.build_inventory()
        lines = ["<b>Platform inventory</b>", f"Services: {len(inv.get('services', {}))}"]
        for name, meta in list(inv.get("services", {}).items())[:8]:
            lines.append(f"• {name} ({meta.get('owner')})")
        lines.append(f"Events: {len(inv.get('event_schemas', {}))} types")
        return "\n".join(lines)

    def dependency_graph_text(self) -> str:
        inv = self.repository.get_inventory() or self.build_inventory()
        deps = inv.get("dependencies", {})
        lines = ["<b>Dependency graph</b>"]
        for node, edges in deps.items():
            lines.append(f"• {node} → {', '.join(edges)}")
        return "\n".join(lines)
