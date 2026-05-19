from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.operational_memory.coordinator import OperationalMemoryCoordinator


def register_opmem_handlers(*, opmem: OperationalMemoryCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _offline() -> str:
        return "Operational memory layer offline."

    @router.message(Command("incident_history"))
    @admin_only("/incident_history")
    async def cmd_incident_history(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.incident_history_html())

    @router.message(Command("recurrent_failures"))
    @admin_only("/recurrent_failures")
    async def cmd_recurrent_failures(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.recurrent_failures_html())

    @router.message(Command("predictive_risk"))
    @admin_only("/predictive_risk")
    async def cmd_predictive_risk(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.prediction.predictive_risk_html())

    @router.message(Command("drift_report"))
    @admin_only("/drift_report")
    async def cmd_drift_report(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.drift.drift_report_html())

    @router.message(Command("seasonality_state"))
    @admin_only("/seasonality_state")
    async def cmd_seasonality_state(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.seasonality.seasonality_state_html())

    @router.message(Command("incident_fingerprint"))
    @admin_only("/incident_fingerprint")
    async def cmd_incident_fingerprint(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        fps = opmem.repository.list_fingerprints(limit=1)
        if not fps:
            await _reply(message, "<b>Incident fingerprint</b>\nNo fingerprints yet.")
            return
        await _reply(message, opmem.fingerprints.html_detail(fps[0]["signature_hash"]))

    @router.message(Command("recovery_patterns"))
    @admin_only("/recovery_patterns")
    async def cmd_recovery_patterns(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.outcomes.recovery_patterns_html())

    @router.message(Command("operational_memory"))
    @admin_only("/operational_memory")
    async def cmd_operational_memory(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.operational_memory_html())

    @router.message(Command("preventive_actions"))
    @admin_only("/preventive_actions")
    async def cmd_preventive_actions(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.recommendations.preventive_actions_html())

    @router.message(Command("risk_forecast"))
    @admin_only("/risk_forecast")
    async def cmd_risk_forecast(message: Message) -> None:
        if opmem is None:
            await message.answer(_offline())
            return
        await _reply(message, opmem.prediction.risk_forecast_html())
