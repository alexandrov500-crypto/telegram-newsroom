from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.live_deploy.coordinator import LiveDeployCoordinator


def register_live_deploy_handlers(*, live_deploy: LiveDeployCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("first_72h_status"))
    @admin_only("/first_72h_status")
    async def cmd_first_72h(message: Message) -> None:
        if live_deploy is None:
            await message.answer("Live deploy layer offline.")
            return
        await _reply(message, live_deploy.first_72h.status_html())

    @router.message(Command("live_deploy_status"))
    @admin_only("/live_deploy_status")
    async def cmd_live_deploy(message: Message) -> None:
        if live_deploy is None:
            await message.answer("Live deploy layer offline.")
            return
        t = await live_deploy.tick()
        await _reply(
            message,
            f"<b>Live deploy</b>\n"
            f"72h: {'active' if t['first_72h_active'] else 'off'}\n"
            f"Hours: {t['hours_elapsed']}\n"
            f"Reports due: {', '.join(t['reports_due']) or 'none'}",
        )
