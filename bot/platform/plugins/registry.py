from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bot.platform.plugins.contracts import PluginCategory, PluginManifest, PluginSandbox
from bot.platform.repository import PlatformRepository

logger = logging.getLogger(__name__)

_BUILTIN_PLUGINS: tuple[PluginManifest, ...] = (
    PluginManifest(
        plugin_id="core.rss_ingest",
        name="RSS Ingest",
        version="1.0.0",
        category=PluginCategory.INGEST_SOURCE,
        capabilities=frozenset({"fetch", "normalize"}),
    ),
    PluginManifest(
        plugin_id="core.ga_quality",
        name="GA Quality Validator",
        version="1.0.0",
        category=PluginCategory.QUALITY_VALIDATOR,
        capabilities=frozenset({"validate", "score"}),
    ),
    PluginManifest(
        plugin_id="core.ops_export",
        name="Ops Metrics Exporter",
        version="1.0.0",
        category=PluginCategory.ANALYTICS_EXPORTER,
        capabilities=frozenset({"export_metrics"}),
    ),
)


@dataclass
class PluginRegistry:
    repository: PlatformRepository
    _sandboxes: dict[str, PluginSandbox] = field(default_factory=dict)

    def bootstrap(self) -> None:
        for m in _BUILTIN_PLUGINS:
            issues = m.validate()
            if issues:
                logger.warning("event=plugin_manifest_invalid id=%s %s", m.plugin_id, issues)
                continue
            self.repository.register_plugin(
                plugin_id=m.plugin_id,
                name=m.name,
                category=m.category.value,
                version=m.version,
                manifest={"min_platform_version": m.min_platform_version},
                capabilities=list(m.capabilities),
                trust_score=0.95,
            )
            self._sandboxes[m.plugin_id] = PluginSandbox(
                plugin_id=m.plugin_id,
                allowed_capabilities=m.capabilities,
            )
            self.repository.plugin_audit(m.plugin_id, "register", {"version": m.version})

    def list_live(self) -> list[dict[str, Any]]:
        return self.repository.list_plugins(enabled_only=True)

    def health_summary(self) -> str:
        plugins = self.list_live()
        lines = ["<b>Plugin health</b>", f"Registered: {len(plugins)}"]
        for p in plugins[:10]:
            mark = "✓" if p.get("health_status") == "healthy" else "!"
            lines.append(
                f"{mark} {p['name']} <code>{p['plugin_id']}</code> "
                f"v{p['version']} trust {p['trust_score']:.2f}",
            )
        return "\n".join(lines)

    def plugins_live_text(self) -> str:
        plugins = self.list_live()
        by_cat: dict[str, list] = {}
        for p in plugins:
            by_cat.setdefault(p["category"], []).append(p)
        lines = ["<b>Plugins live</b>"]
        for cat, items in sorted(by_cat.items()):
            lines.append(f"\n<b>{cat}</b>")
            for p in items[:4]:
                lines.append(f"• {p['name']} ({p['health_status']})")
        return "\n".join(lines)
