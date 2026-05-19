from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.production_safety.coordinator import ProductionSafetyCoordinator
    from bot.storage.editorial_repository import EditorialRepository


def register_production_safety_handlers(
    *,
    safety: ProductionSafetyCoordinator | None,
    editorial: EditorialRepository | None = None,
) -> None:
    async def _reply(message: Message, text: str) -> None:
        if safety is not None and message.from_user:
            safety.security.audit_command(
                str(message.from_user.id),
                (message.text or "")[:32].split()[0],
                args_preview=(message.text or "")[:200],
            )
            safety.operators.record_activity(str(message.from_user.id), command=message.text)
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("safety_status"))
    @admin_only("/safety_status")
    async def cmd_safety_status(message: Message) -> None:
        if safety is None:
            await message.answer("Production safety layer offline.")
            return
        snap = await safety.tick(queue_depth=0)
        lines = [
            "<b>🛡 Production safety</b>",
            f"Rollout: <b>{snap.rollout_stage.value}</b>",
            f"Cost: <b>{snap.cost_mode.value}</b>",
            f"Publish: {'✅' if snap.publish_allowed else '⛔'}",
            f"Telegram success: {snap.telegram.success_ratio * 100:.0f}%",
            f"FloodWait/h: {snap.telegram.floodwait_count_hour}",
            f"Daily spend: ${snap.financial.daily_spend_usd:.2f} / ${snap.financial.daily_cap_usd:.2f}",
            f"Projected: ${snap.financial.projected_daily_usd:.2f}",
            f"Queue: {snap.containment.queue_depth} DLQ: {snap.containment.dlq_depth}",
            f"Breakers: {snap.metadata.get('breakers', {})}",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("rollout_status"))
    @admin_only("/rollout_status")
    async def cmd_rollout_status(message: Message) -> None:
        if safety is None:
            await message.answer("Production safety offline.")
            return
        stage = safety.rollout.current_stage()
        limits = safety.rollout.limits()
        remaining = safety.rollout.publishes_remaining_hour()
        lines = [
            "<b>📡 Rollout</b>",
            f"Stage: <b>{stage.value}</b>",
            f"Publishes left (1h): <b>{remaining}</b>",
            f"Limits: {limits}",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("rollout_rollback"))
    @admin_only("/rollout_rollback")
    async def cmd_rollout_rollback(message: Message) -> None:
        if safety is None:
            await message.answer("Production safety offline.")
            return
        stage = safety.rollout.rollback_to_shadow(reason="operator_command")
        safety.telegram.pause_publish(reason="rollout_rollback")
        await _reply(message, f"⛔ Rolled back to <b>{stage.value}</b>")

    @router.message(Command("publish_resume"))
    @admin_only("/publish_resume")
    async def cmd_publish_resume(message: Message) -> None:
        if safety is None:
            await message.answer("Production safety offline.")
            return
        safety.telegram.resume_publish()
        await _reply(message, "✅ Telegram publish resumed (operator override)")

    @router.message(Command("publish_pause"))
    @admin_only("/publish_pause")
    async def cmd_publish_pause(message: Message) -> None:
        if safety is None:
            await message.answer("Production safety offline.")
            return
        safety.telegram.pause_publish(reason="operator_command")
        await _reply(message, "⛔ Telegram publish paused")

    @router.message(Command("story_trace"))
    @admin_only("/story_trace")
    async def cmd_story_trace(message: Message) -> None:
        if safety is None or editorial is None:
            await message.answer("Trace unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /story_trace <news_id>")
            return
        try:
            news_id = int(parts[1].strip())
        except ValueError:
            await message.answer("Invalid news id.")
            return
        await _reply(message, safety.forensics.story_trace_text(news_id, editorial=editorial))

    @router.message(Command("decision_trace"))
    @admin_only("/decision_trace")
    async def cmd_decision_trace(message: Message) -> None:
        if safety is None:
            await message.answer("Trace unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /decision_trace <news_id>")
            return
        try:
            news_id = int(parts[1].strip())
        except ValueError:
            await message.answer("Invalid news id.")
            return
        await _reply(message, safety.forensics.decision_trace_text(news_id))

    @router.message(Command("operators_live"))
    @admin_only("/operators_live")
    async def cmd_operators_live(message: Message) -> None:
        if safety is None:
            await message.answer("Production safety offline.")
            return
        await _reply(message, safety.operators.escalation_summary())
