from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.ga_ops.coordinator import GaOpsCoordinator


def register_ga_ops_handlers(
    *,
    ga_ops: GaOpsCoordinator | None,
    queue_depth_fn: Any = None,
) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _queue() -> int:
        if queue_depth_fn is None:
            return 0
        try:
            return int(queue_depth_fn())
        except Exception:
            return 0

    @router.message(Command("traffic_guardrails"))
    @admin_only("/traffic_guardrails")
    async def cmd_traffic_guardrails(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        await _reply(message, ga_ops.traffic.summary_text())

    @router.message(Command("publish_load"))
    @admin_only("/publish_load")
    async def cmd_publish_load(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        snap = ga_ops.traffic.snapshot()
        scaling = ga_ops.scaling.evaluate(
            queue_depth=_queue(),
            publishes_hour=int(snap.get("publishes_hour", 0)),
            max_publish_hour=ga_ops.settings.max_publishes_per_hour,
        )
        lines = [
            "<b>Publish load</b>",
            f"Pressure: <code>{snap['pressure']}</code>",
            f"Rate: {snap['publishes_hour']}/h",
            f"Scaling risk: {scaling['scaling_risk_score']:.0%}",
        ]
        if scaling["recommended_actions"]:
            lines.append("→ " + ", ".join(scaling["recommended_actions"][:3]))
        await _reply(message, "\n".join(lines))

    @router.message(Command("quality_live"))
    @admin_only("/quality_live")
    async def cmd_quality_live(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        avg = ga_ops.quality.trend_avg()
        await _reply(
            message,
            f"<b>Quality live</b>\nAvg score (24): <b>{avg:.2f}</b>\n"
            f"Threshold: {ga_ops.quality.min_overall:.2f}",
        )

    @router.message(Command("quality_trace"))
    @admin_only("/quality_trace")
    async def cmd_quality_trace(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /quality_trace <story_id>")
            return
        try:
            story_id = int(parts[1].strip())
        except ValueError:
            await message.answer("Invalid story id.")
            return
        await _reply(message, ga_ops.quality.trace_text(story_id))

    @router.message(Command("ops_advisor"))
    @admin_only("/ops_advisor")
    async def cmd_ops_advisor(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        sig = ga_ops._signals_fn() if ga_ops._signals_fn else {}
        await _reply(
            message,
            ga_ops.advisor.advise(
                queue_depth=_queue(),
                slo_violations=int(sig.get("slo_violations", 0)),
                scaling_risk=float(sig.get("scaling_risk", 0)),
            ),
        )

    @router.message(Command("maintenance_status"))
    @admin_only("/maintenance_status")
    async def cmd_maintenance_status(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        await _reply(message, ga_ops.advisor.maintenance_status())

    @router.message(Command("ga_status"))
    @admin_only("/ga_status")
    async def cmd_ga_status(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        row = ga_ops.repository.get_ga_readiness()
        if row:
            await _reply(
                message,
                f"<b>GA status</b>\nState: <code>{row['state']}</code>\n"
                f"Score: {row['score']:.0%}",
            )
        else:
            result = ga_ops.evaluate_ga()
            await _reply(message, result.summary_text())

    @router.message(Command("ga_evaluate"))
    @admin_only("/ga_evaluate")
    async def cmd_ga_evaluate(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        result = ga_ops.evaluate_ga()
        ga_ops.repository.set_ga_readiness(
            state=result.state.value,
            score=result.score,
            blockers=list(result.blockers),
        )
        await _reply(message, result.summary_text())

    @router.message(Command("production_summary"))
    @admin_only("/production_summary")
    async def cmd_production_summary(message: Message) -> None:
        if ga_ops is None:
            await message.answer("GA ops offline.")
            return
        await _reply(message, ga_ops.production_summary_text())
