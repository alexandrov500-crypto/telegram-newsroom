from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.ops_certification.coordinator import OpsCertificationCoordinator
    from bot.production_safety.coordinator import ProductionSafetyCoordinator
    from bot.rc1.coordinator import Rc1Coordinator


def register_rc1_handlers(
    *,
    rc1: Rc1Coordinator | None,
    ops_cert: OpsCertificationCoordinator | None = None,
    safety: ProductionSafetyCoordinator | None = None,
    queue_depth_fn: Any = None,
) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _sign(message: Message, command: str) -> bool:
        if rc1 is None or ops_cert is None:
            return True
        has_sig = False
        if ops_cert.settings.enabled:
            ops_cert.audit.sign_action(
                str(message.from_user.id if message.from_user else "0"),
                command,
            )
            has_sig = True
        return rc1.lockdown.require_signed_override(has_signature=has_sig, command=command)

    @router.message(Command("config_status"))
    @admin_only("/config_status")
    async def cmd_config_status(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        await _reply(message, rc1.config_status_text())

    @router.message(Command("config_diff"))
    @admin_only("/config_diff")
    async def cmd_config_diff(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        await _reply(message, rc1.config_diff_text())

    @router.message(Command("rc_status"))
    @admin_only("/rc_status")
    async def cmd_rc_status(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        await _reply(message, rc1.lockdown.status_text())

    @router.message(Command("runtime_profile"))
    @admin_only("/runtime_profile")
    async def cmd_runtime_profile(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        rc1.save_profile_snapshot()
        await _reply(message, rc1.profiler.summary_text())

    @router.message(Command("activation_status"))
    @admin_only("/activation_status")
    async def cmd_activation_status(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        sig: dict = {}
        if ops_cert is not None and ops_cert.last_certification:
            sig["certified"] = ops_cert.last_certification.state.value == "CERTIFIED"
        val = rc1.repository.latest_validation_scores()
        conf = float(val["go_live_confidence"]) if val else 0.0
        slo_v = 0
        if ops_cert is not None:
            slo_v = sum(1 for e in ops_cert.slo.evaluate_all() if e.violated)
        trans = rc1.activation.evaluate_next(
            certified=sig.get("certified", False),
            go_live_confidence=conf,
            slo_ok=slo_v == 0,
        )
        await _reply(message, rc1.activation.status_text(transition=trans))

    @router.message(Command("activate_next_stage"))
    @admin_only("/activate_next_stage")
    async def cmd_activate_next_stage(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        if not _sign(message, "activate_next_stage"):
            await message.answer("RC1 lockdown: signed operator action required.")
            return
        certified = False
        if ops_cert is not None and ops_cert.last_certification:
            certified = ops_cert.last_certification.state.value == "CERTIFIED"
        allowed, reason = rc1.lockdown.allow_rollout_escalation(certified=certified)
        if not allowed:
            await message.answer(f"Blocked: {reason}. Run /go_live_certify first.")
            return
        val = rc1.repository.latest_validation_scores() or {}
        trans = rc1.activation.advance(
            operator_id=str(message.from_user.id if message.from_user else "0"),
            snapshot={"tick": "manual"},
            certified=certified,
            go_live_confidence=float(val.get("go_live_confidence", 0)),
            slo_ok=True,
        )
        if trans.allowed and trans.next_stage and safety is not None:
            from bot.production_safety.types import RolloutStage

            target = rc1.activation.rollout_stage_for_current()
            try:
                safety.rollout.set_stage(RolloutStage(target), reason="activation_workflow")
            except ValueError:
                pass
        text = rc1.activation.status_text(transition=trans)
        if not trans.allowed:
            text += "\n\n⛔ Requirements not met."
        await _reply(message, text)

    @router.message(Command("activation_rollback"))
    @admin_only("/activation_rollback")
    async def cmd_activation_rollback(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        if not _sign(message, "activation_rollback"):
            await message.answer("RC1 lockdown: signed operator action required.")
            return
        parts = (message.text or "").split(maxsplit=1)
        reason = parts[1] if len(parts) > 1 else "operator"
        stage = rc1.activation.rollback(
            operator_id=str(message.from_user.id if message.from_user else "0"),
            reason=reason,
        )
        if safety is not None:
            safety.rollout.rollback_to_shadow(reason=reason)
        await message.answer(f"↩️ Rolled back to <code>{stage.value}</code>", parse_mode="HTML")

    @router.message(Command("launch_dashboard"))
    @admin_only("/launch_dashboard")
    async def cmd_launch_dashboard(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        sig: dict[str, Any] = {}
        if ops_cert is not None and ops_cert.last_certification:
            sig["certification"] = ops_cert.last_certification.to_dict()
        if ops_cert is not None:
            sig["slo_violations"] = sum(1 for e in ops_cert.slo.evaluate_all() if e.violated)
        if safety is not None:
            sig["rollout_stage"] = safety.rollout.current_stage().value
        val = rc1.repository.latest_validation_scores()
        if val:
            sig["go_live_confidence"] = val.get("go_live_confidence")
        await _reply(message, rc1.launch_dashboard_text(sig))

    @router.message(Command("operator_digest"))
    @admin_only("/operator_digest")
    async def cmd_operator_digest(message: Message) -> None:
        if rc1 is None:
            await message.answer("RC1 layer offline.")
            return
        await _reply(message, rc1.operator_ux.digest_text())
