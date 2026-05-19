from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.platform.coordinator import PlatformCoordinator


def register_platform_handlers(*, platform: PlatformCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("plugins_live"))
    @admin_only("/plugins_live")
    async def cmd_plugins_live(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.plugins.plugins_live_text())

    @router.message(Command("plugin_health"))
    @admin_only("/plugin_health")
    async def cmd_plugin_health(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.plugins.health_summary())

    @router.message(Command("platform_inventory"))
    @admin_only("/platform_inventory")
    async def cmd_platform_inventory(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.idp.inventory_text())

    @router.message(Command("dependency_graph"))
    @admin_only("/dependency_graph")
    async def cmd_dependency_graph(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.idp.dependency_graph_text())

    @router.message(Command("workflow_live"))
    @admin_only("/workflow_live")
    async def cmd_workflow_live(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.workflows.live_text())

    @router.message(Command("workflow_trace"))
    @admin_only("/workflow_trace")
    async def cmd_workflow_trace(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /workflow_trace <workflow_id>")
            return
        await _reply(message, platform.workflows.trace_text(parts[1].strip()))

    @router.message(Command("graph_insights"))
    @admin_only("/graph_insights")
    async def cmd_graph_insights(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.graph.insights_text())

    @router.message(Command("risk_relations"))
    @admin_only("/risk_relations")
    async def cmd_risk_relations(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.graph.risk_relations_text())

    @router.message(Command("agent_mesh"))
    @admin_only("/agent_mesh")
    async def cmd_agent_mesh(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.cognition.mesh_text())

    @router.message(Command("debate_trace"))
    @admin_only("/debate_trace")
    async def cmd_debate_trace(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /debate_trace <story_id>")
            return
        try:
            story_id = int(parts[1].strip())
        except ValueError:
            await message.answer("story_id must be an integer")
            return
        await _reply(message, platform.cognition.debate_trace_text(story_id))

    @router.message(Command("policy_status"))
    @admin_only("/policy_status")
    async def cmd_policy_status(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.policies.status_text())

    @router.message(Command("policy_diff"))
    @admin_only("/policy_diff")
    async def cmd_policy_diff(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        kind = parts[1].strip() if len(parts) > 1 else "publish"
        await _reply(message, platform.policies.diff_text(kind))

    @router.message(Command("platform_health"))
    @admin_only("/platform_health")
    async def cmd_platform_health(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        if platform._last_snapshot is None:
            await platform.tick()
        await _reply(message, platform.platform_health_text())

    @router.message(Command("topology_snapshot"))
    @admin_only("/topology_snapshot")
    async def cmd_topology_snapshot(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        if platform._last_snapshot is None:
            await platform.tick()
        await _reply(message, platform.topology_snapshot_text())

    @router.message(Command("ecosystem_risk"))
    @admin_only("/ecosystem_risk")
    async def cmd_ecosystem_risk(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        if platform._last_snapshot is None:
            await platform.tick()
        await _reply(message, platform.ecosystem_risk_text())

    @router.message(Command("governance_audit"))
    @admin_only("/governance_audit")
    async def cmd_governance_audit(message: Message) -> None:
        if platform is None:
            await message.answer("Platform layer offline.")
            return
        await _reply(message, platform.governance_audit_text())
