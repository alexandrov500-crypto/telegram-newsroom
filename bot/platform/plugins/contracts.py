from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class PluginCategory(str, Enum):
    INGEST_SOURCE = "ingest_source"
    COGNITION_ENRICHER = "cognition_enricher"
    MODERATION_FILTER = "moderation_filter"
    ANALYTICS_EXPORTER = "analytics_exporter"
    OPERATOR_TOOL = "operator_tool"
    QUALITY_VALIDATOR = "quality_validator"


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    category: PluginCategory
    capabilities: frozenset[str]
    config_scope: str = "tenant:default"
    min_platform_version: str = "1.0.0"

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.plugin_id or not self.name:
            issues.append("missing_id_or_name")
        if not self.capabilities:
            issues.append("no_capabilities")
        return issues


PluginHook = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class PluginSandbox:
    """Isolation boundary — failures contained per plugin."""

    plugin_id: str
    allowed_capabilities: frozenset[str]
    _handler: PluginHook | None = None
    failure_count: int = 0
    max_failures: int = 5

    async def execute(self, payload: dict[str, Any], *, capability: str) -> dict[str, Any]:
        if capability not in self.allowed_capabilities:
            return {"ok": False, "error": "capability_denied"}
        if self.failure_count >= self.max_failures:
            return {"ok": False, "error": "plugin_quarantined"}
        if self._handler is None:
            return {"ok": True, "noop": True}
        try:
            result = await self._handler(payload)
            return {"ok": True, **result}
        except Exception as exc:
            self.failure_count += 1
            return {"ok": False, "error": str(exc)[:200]}
