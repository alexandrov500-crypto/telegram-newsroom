from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.ops_playbook.coordinator import OpsPlaybookCoordinator


def register_ops_playbook_handlers(*, playbook: OpsPlaybookCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _uid(message: Message) -> str:
        return str(message.from_user.id) if message.from_user else "operator"

    def _sig() -> dict:
        if playbook is None or playbook._signals_fn is None:
            return {}
        return playbook._signals_fn()

    @router.message(Command("shift_handoff"))
    @admin_only("/shift_handoff")
    async def cmd_shift_handoff(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.shift_handoff_text())

    @router.message(Command("take_shift"))
    @admin_only("/take_shift")
    async def cmd_take_shift(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.shift.take_shift(_uid(message), _sig()))

    @router.message(Command("handoff_ack"))
    @admin_only("/handoff_ack")
    async def cmd_handoff_ack(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.shift.acknowledge(_uid(message)))

    @router.message(Command("war_room_start"))
    @admin_only("/war_room_start")
    async def cmd_war_room_start(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /war_room_start <incident_id>")
            return
        await _reply(
            message,
            playbook.war_room.start(parts[1].strip(), _sig()),
        )

    @router.message(Command("war_room_status"))
    @admin_only("/war_room_status")
    async def cmd_war_room_status(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        iid = parts[1].strip() if len(parts) > 1 else None
        await _reply(message, playbook.war_room.status(iid))

    @router.message(Command("war_room_stop"))
    @admin_only("/war_room_stop")
    async def cmd_war_room_stop(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            active = playbook.repository.active_war_room()
            if not active:
                await message.answer("No active war room.")
                return
            iid = active["incident_id"]
        else:
            iid = parts[1].strip()
        await _reply(message, playbook.war_room.stop(iid))

    @router.message(Command("campaign_mode_start"))
    @admin_only("/campaign_mode_start")
    async def cmd_campaign_start(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        ctype = parts[1].strip() if len(parts) > 1 else "breaking"
        await _reply(message, playbook.campaign.start(ctype))

    @router.message(Command("campaign_mode_stop"))
    @admin_only("/campaign_mode_stop")
    async def cmd_campaign_stop(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.campaign.stop())

    @router.message(Command("campaign_status"))
    @admin_only("/campaign_status")
    async def cmd_campaign_status(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.campaign.status())

    @router.message(Command("training_mode"))
    @admin_only("/training_mode")
    async def cmd_training_mode(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip().lower() in ("off", "stop", "0"):
            await _reply(message, playbook.training.disable_training_mode())
        else:
            await _reply(message, playbook.training.enable_training_mode())

    @router.message(Command("run_drill"))
    @admin_only("/run_drill")
    async def cmd_run_drill(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /run_drill <scenario>")
            return
        _, text = playbook.training.run_drill(parts[1].strip(), _uid(message))
        await _reply(message, text)

    @router.message(Command("drill_results"))
    @admin_only("/drill_results")
    async def cmd_drill_results(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.training.results_html())

    @router.message(Command("channel_reputation"))
    @admin_only("/channel_reputation")
    async def cmd_channel_reputation(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        playbook.reputation.ingest(_sig())
        await _reply(message, playbook.reputation.reputation_html())

    @router.message(Command("trust_volatility"))
    @admin_only("/trust_volatility")
    async def cmd_trust_volatility(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.reputation.volatility_html())

    @router.message(Command("exec_incident_brief"))
    @admin_only("/exec_incident_brief")
    async def cmd_exec_brief(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /exec_incident_brief <incident_id>")
            return
        iid = parts[1].strip()
        sig = _sig()
        sig["war_room_active"] = bool(playbook.repository.active_war_room())
        await _reply(message, playbook.executive.from_signals(iid, sig))

    @router.message(Command("ops_audit"))
    @admin_only("/ops_audit")
    async def cmd_ops_audit(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.auditor.audit_html(_sig()))

    @router.message(Command("compliance_status"))
    @admin_only("/compliance_status")
    async def cmd_compliance_status(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.auditor.compliance_status_html())

    @router.message(Command("launch_period_status"))
    @admin_only("/launch_period_status")
    async def cmd_launch_period(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.launch_period.status_html())

    @router.message(Command("daily_ops_summary"))
    @admin_only("/daily_ops_summary")
    async def cmd_daily_ops(message: Message) -> None:
        if playbook is None:
            await message.answer("Ops playbook offline.")
            return
        await _reply(message, playbook.rhythm.daily_html(_sig()))
