from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.ops_evolution.coordinator import OpsEvolutionCoordinator


def register_ops_evolution_handlers(*, evolution: OpsEvolutionCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _signals() -> dict:
        if evolution is None or evolution._signals_fn is None:
            return {}
        return evolution._signals_fn()

    @router.message(Command("ops_memory"))
    @admin_only("/ops_memory")
    async def cmd_ops_memory(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.memory.summary_text())

    @router.message(Command("incident_patterns"))
    @admin_only("/incident_patterns")
    async def cmd_incident_patterns(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.memory.patterns_text())

    @router.message(Command("recovery_history"))
    @admin_only("/recovery_history")
    async def cmd_recovery_history(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        key = parts[1].strip() if len(parts) > 1 else None
        await _reply(message, evolution.memory.recovery_history_text(key))

    @router.message(Command("strategic_optimizations"))
    @admin_only("/strategic_optimizations")
    async def cmd_strategic_optimizations(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.strategy.list_pending_text())

    @router.message(Command("optimization_impact"))
    @admin_only("/optimization_impact")
    async def cmd_optimization_impact(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /optimization_impact <proposal_id_prefix>")
            return
        await _reply(message, evolution.strategy.impact_text(parts[1].strip()))

    @router.message(Command("narrative_health"))
    @admin_only("/narrative_health")
    async def cmd_narrative_health(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.cognition.narrative_health_text())

    @router.message(Command("editorial_diversity"))
    @admin_only("/editorial_diversity")
    async def cmd_editorial_diversity(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.cognition.editorial_diversity_text())

    @router.message(Command("ops_assistant"))
    @admin_only("/ops_assistant")
    async def cmd_ops_assistant(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /ops_assistant <question>")
            return
        await _reply(
            message,
            evolution.assistant.answer(parts[1], signals=_signals()),
        )

    @router.message(Command("why_alert"))
    @admin_only("/why_alert")
    async def cmd_why_alert(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /why_alert <id>")
            return
        await _reply(
            message,
            evolution.assistant.explain_alert(parts[1].strip(), signals=_signals()),
        )

    @router.message(Command("maintenance_plan"))
    @admin_only("/maintenance_plan")
    async def cmd_maintenance_plan(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.maintenance.plan_text())

    @router.message(Command("maintenance_risk"))
    @admin_only("/maintenance_risk")
    async def cmd_maintenance_risk(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.maintenance.risk_text(signals=_signals()))

    @router.message(Command("maturity_status"))
    @admin_only("/maturity_status")
    async def cmd_maturity_status(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.maturity.status_text(_signals()))

    @router.message(Command("maturity_trends"))
    @admin_only("/maturity_trends")
    async def cmd_maturity_trends(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.maturity.trends_text())

    @router.message(Command("evolution_report"))
    @admin_only("/evolution_report")
    async def cmd_evolution_report(message: Message) -> None:
        if evolution is None:
            await message.answer("Ops evolution offline.")
            return
        await _reply(message, evolution.evolution_report_text())
