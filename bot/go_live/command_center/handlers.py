from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.go_live.coordinator import GoLiveCoordinator


def register_go_live_handlers(*, go_live: GoLiveCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("startup_check"))
    @admin_only("/startup_check")
    async def cmd_startup_check(message: Message) -> None:
        if go_live is None:
            await message.answer("Go-live layer offline.")
            return
        await _reply(message, go_live.startup_check_text())

    @router.message(Command("production_ready"))
    @admin_only("/production_ready")
    async def cmd_production_ready(message: Message) -> None:
        if go_live is None:
            await message.answer("Go-live layer offline.")
            return
        await _reply(message, go_live.production_ready_text())

    @router.message(Command("channel_status"))
    @admin_only("/channel_status")
    async def cmd_channel_status(message: Message) -> None:
        if go_live is None:
            await message.answer("Go-live layer offline.")
            return
        await _reply(message, go_live.channel_status_text())

    @router.message(Command("first_publication_status"))
    @admin_only("/first_publication_status")
    async def cmd_first_publication_status(message: Message) -> None:
        if go_live is None:
            await message.answer("Go-live layer offline.")
            return
        sig = go_live._signals_fn() if go_live._signals_fn else {}
        allowed, nxt, gates = go_live.first_publication.evaluate_advance(
            ga_ready=bool(sig.get("ga_ready")),
            certified=bool(sig.get("certified")),
            confidence=float(sig.get("go_live_confidence", 0)),
            slo_ok=bool(sig.get("slo_ok", True)),
            operator_signoff=False,
        )
        await _reply(
            message,
            go_live.first_publication.status_html(gates=gates, next_stage=nxt)
            + f"\n\nAdvance: {'ready' if allowed else 'blocked'}",
        )

    @router.message(Command("advance_publication"))
    @admin_only("/advance_publication")
    async def cmd_advance_publication(message: Message) -> None:
        if go_live is None:
            await message.answer("Go-live layer offline.")
            return
        uid = str(message.from_user.id) if message.from_user else "operator"
        sig = go_live._signals_fn() if go_live._signals_fn else {}
        nxt, gates = go_live.first_publication.advance(
            operator_id=uid,
            snapshot=sig,
            ga_ready=bool(sig.get("ga_ready")),
            certified=bool(sig.get("certified")),
            confidence=float(sig.get("go_live_confidence", 0)),
            slo_ok=bool(sig.get("slo_ok", True)),
        )
        if nxt is None:
            await _reply(
                message,
                go_live.first_publication.status_html(gates=gates)
                + "\n\n<b>Blocked</b> — resolve gates first.",
            )
            return
        await _reply(
            message,
            f"<b>Advanced</b> → <code>{nxt.value}</code>\n"
            f"Set env: PRODUCTION_ROLLOUT_STAGE={go_live.first_publication.rollout_for(nxt)}\n"
            f"RELIABILITY_PUBLISH_MODE={go_live.first_publication.reliability_mode_for(nxt)}",
        )
