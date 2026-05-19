from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message
from bot.ops_certification.chaos.scenarios import ChaosScenario

if TYPE_CHECKING:
    from bot.ops_certification.coordinator import OpsCertificationCoordinator
    from bot.production_safety.coordinator import ProductionSafetyCoordinator
    from bot.reliability.coordinator import ReliabilityCoordinator


def register_ops_certification_handlers(
    *,
    ops_cert: OpsCertificationCoordinator | None,
    reliability: ReliabilityCoordinator | None = None,
    safety: ProductionSafetyCoordinator | None = None,
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

    def _audit_cmd(message: Message, command: str) -> None:
        if ops_cert is None:
            return
        ops_cert.audit.sign_action(
            str(message.from_user.id if message.from_user else "unknown"),
            command,
        )
        ops_cert.security.record_admin_action(
            str(message.from_user.id if message.from_user else "unknown"),
        )

    @router.message(Command("chaos_status"))
    @admin_only("/chaos_status")
    async def cmd_chaos_status(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        _audit_cmd(message, "chaos_status")
        runs = ops_cert.repository.latest_chaos_runs(5)
        active = ops_cert.last_chaos
        lines = ["<b>Chaos status</b>", f"Enabled: {ops_cert.settings.chaos_enabled}"]
        if active:
            lines.append(f"Last: {active.scenario.value} · {active.status}")
        for r in runs[:3]:
            lines.append(f"• {r['scenario']}: {r['status']} ({r['survivability_score']:.2f})")
        lines.append("\nScenarios: " + ", ".join(ops_cert.chaos.list_scenarios()[:4]) + "…")
        await _reply(message, "\n".join(lines))

    @router.message(Command("chaos_run"))
    @admin_only("/chaos_run")
    async def cmd_chaos_run(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /chaos_run <scenario>")
            return
        _audit_cmd(message, "chaos_run")
        name = parts[1].strip().lower()
        try:
            scenario = ChaosScenario(name)
        except ValueError:
            await message.answer(f"Unknown scenario. Try: {', '.join(s.value for s in ChaosScenario)}")
            return

        async def _rollback(reason: str) -> None:
            if safety is not None:
                safety.rollout.rollback_to_shadow(reason=reason)

        result = await ops_cert.run_chaos(scenario, on_rollback=_rollback)
        await _reply(message, result.summary())

    @router.message(Command("slo_live"))
    @admin_only("/slo_live")
    async def cmd_slo_live(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        _audit_cmd(message, "slo_live")
        lines = ["<b>SLO live</b>"]
        for ev in ops_cert.slo.evaluate_all():
            mark = "✓" if not ev.violated else "⛔"
            lines.append(
                f"{mark} {ev.name.value}: {ev.compliance_ratio:.1%} "
                f"burn {ev.burn_rate:.2f}",
            )
        await _reply(message, "\n".join(lines))

    @router.message(Command("error_budget"))
    @admin_only("/error_budget")
    async def cmd_error_budget(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        summary = ops_cert.slo.error_budget_summary()
        lines = [
            "<b>Error budget</b>",
            f"Violations: {summary['violated_count']}",
            f"Critical burn: {summary['critical_burn']:.2f}",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("certification_status"))
    @admin_only("/certification_status")
    async def cmd_certification_status(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        cert = ops_cert.last_certification or ops_cert.certify()
        await _reply(message, cert.summary_text())

    @router.message(Command("go_live_certify"))
    @admin_only("/go_live_certify")
    async def cmd_go_live_certify(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        _audit_cmd(message, "go_live_certify")
        cert = ops_cert.certify()
        await _reply(message, cert.summary_text())

    @router.message(Command("security_status"))
    @admin_only("/security_status")
    async def cmd_security_status(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        snap = ops_cert.security.snapshot()
        lines = [
            "<b>Security status</b>",
            f"Audit chain: active",
            f"Admin sessions tracked: {len(snap.get('admin_activity', {}))}",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("audit_trace"))
    @admin_only("/audit_trace")
    async def cmd_audit_trace(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /audit_trace <action_id>")
            return
        await _reply(message, ops_cert.audit.trace_text(parts[1].strip()))

    @router.message(Command("incident_review"))
    @admin_only("/incident_review")
    async def cmd_incident_review(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident_review <id>")
            return
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        text = await ops_cert.incidents.review(
            parts[1].strip(),
            reliability=reliability,
            operator_console=console,
        )
        await _reply(message, text)

    @router.message(Command("freeze_editorial"))
    @admin_only("/freeze_editorial")
    async def cmd_freeze_editorial(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        _audit_cmd(message, "freeze_editorial")
        parts = (message.text or "").split()
        if len(parts) > 1 and parts[1].lower() == "off":
            ops_cert.governance.unfreeze_editorial()
            await message.answer("Editorial unfrozen.")
        else:
            ops_cert.governance.freeze_editorial(reason="operator_command")
            await message.answer("⛔ Editorial frozen.")

    @router.message(Command("governance_status"))
    @admin_only("/governance_status")
    async def cmd_governance_status(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        await _reply(message, ops_cert.governance.summary_text())

    @router.message(Command("exec_report"))
    @admin_only("/exec_report")
    async def cmd_exec_report(message: Message) -> None:
        if ops_cert is None:
            await message.answer("Ops certification offline.")
            return
        _audit_cmd(message, "exec_report")
        cert = ops_cert.last_certification or ops_cert.certify()
        report = ops_cert.reporting.build_daily(
            certification=cert,
            slo_engine=ops_cert.slo,
            stability_score=float(
                (cert.to_dict() if cert else {}).get("score", 0.85),
            ),
            ai_spend_usd=0.0,
            publish_count=0,
            incident_count=0,
        )
        await _reply(message, ops_cert.reporting.format_telegram(report))
