from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.week1.coordinator import Week1Coordinator


def register_week1_handlers(*, week1: Week1Coordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _sig() -> dict:
        if week1 is None or week1._signals_fn is None:
            return {}
        return week1._signals_fn()

    @router.message(Command("alert_quality"))
    @admin_only("/alert_quality")
    async def cmd_alert_quality(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.alerts.alert_quality_html())

    @router.message(Command("noise_index"))
    @admin_only("/noise_index")
    async def cmd_noise_index(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.alerts.noise_index_html())

    @router.message(Command("quality_adaptation"))
    @admin_only("/quality_adaptation")
    async def cmd_quality_adaptation(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.quality.adaptation_html(_sig()))

    @router.message(Command("audience_fatigue"))
    @admin_only("/audience_fatigue")
    async def cmd_audience_fatigue(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.quality.audience_fatigue_html())

    @router.message(Command("ops_copilot"))
    @admin_only("/ops_copilot")
    async def cmd_ops_copilot(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.copilot.summarize(_sig()))

    @router.message(Command("what_changed_24h"))
    @admin_only("/what_changed_24h")
    async def cmd_what_changed(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.copilot.what_changed_24h(_sig()))

    @router.message(Command("stabilization_risk"))
    @admin_only("/stabilization_risk")
    async def cmd_stab_risk(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.risk.stabilization_html(_sig()))

    @router.message(Command("rollback_probability"))
    @admin_only("/rollback_probability")
    async def cmd_rollback_prob(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.risk.rollback_probability_html(_sig()))

    @router.message(Command("week1_report"))
    @admin_only("/week1_report")
    async def cmd_week1_report(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        sig = _sig()
        week1.survivability.compute(sig)
        await _reply(message, week1.reporting.week1_report(sig))

    @router.message(Command("launch_confidence"))
    @admin_only("/launch_confidence")
    async def cmd_launch_confidence(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.reporting.launch_confidence(_sig()))

    @router.message(Command("adaptive_recommendations"))
    @admin_only("/adaptive_recommendations")
    async def cmd_adaptive_recs(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        week1.optimization.propose_from_signals(_sig())
        await _reply(message, week1.optimization.recommendations_html())

    @router.message(Command("optimization_safety"))
    @admin_only("/optimization_safety")
    async def cmd_opt_safety(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.optimization.safety_html())

    @router.message(Command("survivability"))
    @admin_only("/survivability")
    async def cmd_survivability(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        week1.survivability.compute(_sig())
        await _reply(message, week1.survivability.survivability_html())

    @router.message(Command("confidence_trend"))
    @admin_only("/confidence_trend")
    async def cmd_confidence_trend(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.survivability.confidence_trend_html())

    @router.message(Command("week1_baselines"))
    @admin_only("/week1_baselines")
    async def cmd_baselines(message: Message) -> None:
        if week1 is None:
            await message.answer("Week-1 stabilization offline.")
            return
        await _reply(message, week1.baseline.status_html())
