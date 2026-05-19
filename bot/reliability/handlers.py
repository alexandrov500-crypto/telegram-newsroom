from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message
from bot.reliability.types import HealthState

if TYPE_CHECKING:
    from bot.reliability.coordinator import ReliabilityCoordinator


def register_reliability_handlers(*, reliability: ReliabilityCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("health_live"))
    @admin_only("/health_live")
    async def cmd_health_live(message: Message) -> None:
        if reliability is None:
            await message.answer("Reliability layer offline.")
            return
        snap = reliability.health.probe()
        emoji = {
            HealthState.HEALTHY: "🟢",
            HealthState.DEGRADED: "🟡",
            HealthState.CRITICAL: "🟠",
            HealthState.FAILED: "🔴",
        }.get(snap.overall_state, "⚪")
        lines = [
            f"<b>{emoji} Health live</b>",
            f"State: <b>{snap.overall_state.value}</b> · score {snap.health_score:.2f}",
            f"Uptime: {snap.uptime_sec / 3600:.1f}h · queue {snap.queue_depth}",
            f"Errors/h: {snap.errors_per_hour:.0f} · retries {snap.retries_per_hour}",
            f"Mode: {snap.publish_mode.value}",
        ]
        if snap.stuck_pipeline:
            lines.append("⚠️ Pipeline may be stuck")
        for s in snap.subsystems:
            mark = "✓" if s.state == HealthState.HEALTHY else "!"
            lines.append(
                f"{mark} {s.name.value}: {s.state.value} ({s.last_heartbeat_sec:.0f}s)",
            )
        await _reply(message, "\n".join(lines))

    @router.message(Command("queues_live"))
    @admin_only("/queues_live")
    async def cmd_queues_live(message: Message) -> None:
        if reliability is None:
            await message.answer("Reliability layer offline.")
            return
        snap = reliability.health.last_snapshot or reliability.health.probe()
        gate = reliability.publish_gate.evaluate(
            health_state=snap.overall_state,
            health_score=snap.health_score,
            queue_depth=snap.queue_depth,
            cognition_latency_ms=0.0,
            telegram_failure_rate=0.0,
            fatal_incidents_recent=reliability.incidents.recent_fatal_count(),
        )
        lines = [
            "<b>📬 Queues live</b>",
            f"Depth: <b>{snap.queue_depth}</b>",
            f"Publish gate: {gate.summary()}",
            f"Stuck: {'yes' if snap.stuck_pipeline else 'no'}",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("incidents_live"))
    @admin_only("/incidents_live")
    async def cmd_incidents_live(message: Message) -> None:
        if reliability is None:
            await message.answer("Reliability layer offline.")
            return
        rows = reliability.incidents._lifecycle.list_open(limit=10)
        if not rows:
            await _reply(message, "<b>Incidents live</b>\nNo open incidents ✅")
            return
        lines = ["<b>🚨 Incidents live</b>"]
        for r in rows:
            lines.append(
                f"• <code>{r['incident_id']}</code> "
                f"[{r.get('severity', '?')}] {r.get('title', '')[:50]}",
            )
        lines.append("\n/incident_ack · /recovery_live")
        await _reply(message, "\n".join(lines))

    @router.message(Command("costs_live"))
    @admin_only("/costs_live")
    async def cmd_costs_live(message: Message) -> None:
        if reliability is None:
            await message.answer("Reliability layer offline.")
            return
        agg = reliability.metrics.aggregate(health=reliability.health.last_snapshot)
        lines = [
            "<b>💰 Costs live</b>",
            f"Token spend (est): <b>${agg.token_usd:.2f}</b>",
            f"Stories processed: {agg.stories_processed}",
            f"Publish success: {agg.publish_success_rate * 100:.1f}%",
            f"Cognition latency: {agg.cognition_latency_ms:.0f}ms",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("recovery_live"))
    @admin_only("/recovery_live")
    async def cmd_recovery_live(message: Message) -> None:
        if reliability is None:
            await message.answer("Reliability layer offline.")
            return
        attempts = reliability.watchdog.recent_attempts()
        lines = ["<b>🔧 Recovery live</b>"]
        if not attempts:
            lines.append("No recent recovery attempts.")
        for a in attempts[-8:]:
            mark = "✓" if a.success else "✗"
            lines.append(
                f"{mark} {a.subsystem}/{a.action} #{a.attempt} — {a.detail[:40]}",
            )
        snap = reliability.health.last_snapshot
        if snap:
            lines.append(f"\nHealth: {snap.overall_state.value} ({snap.health_score:.2f})")
        await _reply(message, "\n".join(lines))
