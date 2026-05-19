from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.post_ga.coordinator import PostGaCoordinator


def register_post_ga_handlers(*, post_ga: PostGaCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("traffic_calibration"))
    @admin_only("/traffic_calibration")
    async def cmd_traffic_calibration(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.calibration.summary_text())

    @router.message(Command("audience_health"))
    @admin_only("/audience_health")
    async def cmd_audience_health(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.calibration.audience_health_text())

    @router.message(Command("quality_trends"))
    @admin_only("/quality_trends")
    async def cmd_quality_trends(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.quality.trends_text())

    @router.message(Command("source_quality"))
    @admin_only("/source_quality")
    async def cmd_source_quality(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.quality.source_quality_text())

    @router.message(Command("operator_load"))
    @admin_only("/operator_load")
    async def cmd_operator_load(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.operator_load.load_text())

    @router.message(Command("attention_risk"))
    @admin_only("/attention_risk")
    async def cmd_attention_risk(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.operator_load.attention_risk_text())

    @router.message(Command("risk_forecast"))
    @admin_only("/risk_forecast")
    async def cmd_risk_forecast(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.risk.forecast_text())

    @router.message(Command("future_pressure"))
    @admin_only("/future_pressure")
    async def cmd_future_pressure(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        fc = post_ga._last_forecast or {}
        await _reply(message, post_ga.risk.future_pressure_text(fc))

    @router.message(Command("governance_trends"))
    @admin_only("/governance_trends")
    async def cmd_governance_trends(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.governance.trends_text())

    @router.message(Command("trust_evolution"))
    @admin_only("/trust_evolution")
    async def cmd_trust_evolution(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.governance.trust_evolution_text())

    @router.message(Command("live_exec"))
    @admin_only("/live_exec")
    async def cmd_live_exec(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.live_exec_text())

    @router.message(Command("optimization_pending"))
    @admin_only("/optimization_pending")
    async def cmd_optimization_pending(message: Message) -> None:
        if post_ga is None:
            await message.answer("Post-GA tuning offline.")
            return
        await _reply(message, post_ga.optimizer.list_pending_text())
