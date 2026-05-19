from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.live_ops.coordinator import LiveOpsCoordinator
    from bot.production_safety.coordinator import ProductionSafetyCoordinator
    from bot.reliability.coordinator import ReliabilityCoordinator


def register_live_ops_handlers(
    *,
    live_ops: LiveOpsCoordinator | None,
    reliability: ReliabilityCoordinator | None = None,
    safety: ProductionSafetyCoordinator | None = None,
    queue_depth_fn: Any = None,
) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _queue_depth() -> int:
        if queue_depth_fn is None:
            return 0
        try:
            return int(queue_depth_fn())
        except Exception:
            return 0

    @router.message(Command("go_live_check"))
    @admin_only("/go_live_check")
    async def cmd_go_live_check(message: Message) -> None:
        if live_ops is None:
            await message.answer("Live ops layer offline.")
            return
        rel_score: float | None = None
        safety_ok = True
        if reliability is not None and reliability.health.last_snapshot:
            rel_score = reliability.health.last_snapshot.health_score
        if safety is not None:
            try:
                snap = await safety.tick(queue_depth=_queue_depth())
                c = snap.containment
                safety_ok = not (c.throttled or c.ingest_paused or c.memory_pressure)
            except Exception:
                safety_ok = False
        readiness = live_ops.go_live_readiness(
            reliability_score=rel_score,
            safety_ok=safety_ok,
            queue_depth=_queue_depth(),
        )
        emoji = "✅" if readiness["ready"] else "⛔"
        lines = [
            f"<b>{emoji} Go-live check</b>",
            f"Ready: <b>{'yes' if readiness['ready'] else 'no'}</b>",
        ]
        for b in readiness.get("blockers", []):
            lines.append(f"• blocker: {b}")
        snap = readiness["snapshot"]
        lines.append(
            f"Stability {snap['stability_score']:.2f} ({snap['stability_forecast']}) · "
            f"bus pending {snap['event_bus_pending']} dlq {snap['event_bus_dlq']}",
        )
        await _reply(message, "\n".join(lines))
        live_ops.telemetry.record_operator_action("go_live_check")

    @router.message(Command("system_risk"))
    @admin_only("/system_risk")
    async def cmd_system_risk(message: Message) -> None:
        lines = ["<b>System risk</b>"]
        if reliability is not None:
            snap = reliability.health.probe()
            lines.append(f"Health: {snap.overall_state.value} · {snap.health_score:.2f}")
            lines.append(f"Queue {snap.queue_depth} · errors/h {snap.errors_per_hour:.0f}")
        if safety is not None:
            ps = await safety.tick(queue_depth=_queue_depth())
            lines.append(f"Rollout: {ps.rollout_stage.value} · cost {ps.cost_mode.value}")
            if ps.containment.throttled or ps.containment.ingest_paused:
                lines.append("⚠️ Containment active")
        if live_ops is not None:
            s = await live_ops.tick(queue_depth=_queue_depth())
            lines.append(f"Stability {s.stability_score:.2f} · forecast {s.stability_forecast}")
        await _reply(message, "\n".join(lines))

    @router.message(Command("publish_pressure"))
    @admin_only("/publish_pressure")
    async def cmd_publish_pressure(message: Message) -> None:
        depth = _queue_depth()
        pending = live_ops.event_bus.pending_count if live_ops else 0
        dlq = live_ops.event_bus.dead_letter_count if live_ops else 0
        lines = [
            "<b>Publish pressure</b>",
            f"Editorial queue: <b>{depth}</b>",
            f"Event bus pending: {pending} · DLQ {dlq}",
        ]
        if safety is not None:
            ps = await safety.tick(queue_depth=depth)
            lines.append(f"Telegram pacing: flood/h {ps.telegram.floodwait_count_hour}")
        await _reply(message, "\n".join(lines))

    @router.message(Command("tenant_status"))
    @admin_only("/tenant_status")
    async def cmd_tenant_status(message: Message) -> None:
        if live_ops is None:
            await message.answer("Live ops offline.")
            return
        tenants = live_ops.tenants.list_tenants()
        lines = ["<b>Tenant status</b>", f"Tenants: {', '.join(tenants)}"]
        for cid, scope in list(live_ops.tenants._channels.items())[:8]:
            lines.append(
                f"• ch {cid}: {scope.tenant_id} · {scope.rollout_stage.value} · "
                f"{scope.cognition_strategy}",
            )
        await _reply(message, "\n".join(lines))

    @router.message(Command("worker_mesh"))
    @admin_only("/worker_mesh")
    async def cmd_worker_mesh(message: Message) -> None:
        if live_ops is None:
            await message.answer("Live ops offline.")
            return
        workers = live_ops.workers.snapshot()
        stale = live_ops.workers.stale_workers()
        lines = [
            "<b>Worker mesh</b>",
            f"Registered: {len(workers)} · stale {len(stale)}",
        ]
        for w in workers[:12]:
            mark = "✓" if w["age_sec"] < 90 else "!"
            lines.append(f"{mark} {w['role']}@{w['node_id']} {w['status']}")
        await _reply(message, "\n".join(lines))

    @router.message(Command("recovery_state"))
    @admin_only("/recovery_state")
    async def cmd_recovery_state(message: Message) -> None:
        if live_ops is None:
            await message.answer("Live ops offline.")
            return
        rep = live_ops.recovery_report
        if rep is None:
            rep = await live_ops.recovery.run_startup_recovery(event_bus=live_ops.event_bus)
        await _reply(message, rep.summary())

    @router.message(Command("eventbus_live"))
    @admin_only("/eventbus_live")
    async def cmd_eventbus_live(message: Message) -> None:
        if live_ops is None:
            await message.answer("Live ops offline.")
            return
        snap = live_ops.event_bus.snapshot()
        tel = snap.get("telemetry", {})
        lines = [
            "<b>Event bus live</b>",
            f"Pending {snap['pending']} · DLQ {snap['dlq']}",
        ]
        handlers = snap.get("handlers", {})
        if handlers:
            lines.append("Handlers: " + ", ".join(f"{k}={v}" for k, v in list(handlers.items())[:6]))
        pub = tel.get("published", {})
        if pub:
            top = sorted(pub.items(), key=lambda x: -x[1])[:5]
            lines.append("Top events: " + ", ".join(f"{k}:{v}" for k, v in top))
        await _reply(message, "\n".join(lines))
