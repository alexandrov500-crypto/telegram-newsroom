from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from aiogram import Bot

from bot.go_live.first_publication import FirstPublicationWorkflow
from bot.go_live.repository import GoLiveRepository
from bot.go_live.settings import GoLiveSettings
from bot.go_live.telegram_activation import ProductionActivationReport, ProductionTelegramActivation
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


@dataclass
class GoLiveCoordinator:
    settings: GoLiveSettings
    repository: GoLiveRepository
    first_publication: FirstPublicationWorkflow
    _last_activation: ProductionActivationReport | None = None
    _signals_fn: Callable[[], dict[str, Any]] | None = None

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def run_production_activation(
        self,
        bot: Bot,
        *,
        channel_id: int,
        operator_chat_id: int | None,
        admin_user_ids: frozenset[int],
        shadow_publish_only: bool,
        emergency_contacts: frozenset[int],
        send_ping: bool = True,
        send_dashboard: bool = True,
    ) -> ProductionActivationReport:
        activation = ProductionTelegramActivation(
            bot,
            channel_id=channel_id,
            operator_chat_id=operator_chat_id,
            admin_user_ids=admin_user_ids,
            strict_permissions=self.settings.strict_channel_permissions,
            run_publish_probe=self.settings.startup_publish_probe,
        )
        report = await activation.run(shadow_publish_only=shadow_publish_only)
        self._last_activation = report

        if not self.repository.get_state():
            self.repository.set_state(
                publication_stage="INTERNAL_SHADOW",
                rollout_stage="INTERNAL_SHADOW",
            )

        if send_ping and operator_chat_id and report.passed:
            await self._startup_operator_ping(bot, operator_chat_id, report)
        if send_dashboard and operator_chat_id:
            await self._executive_dashboard_push(bot, operator_chat_id, report)
        if emergency_contacts and operator_chat_id:
            await self._register_emergency_contacts(bot, operator_chat_id, emergency_contacts)

        return report

    async def _startup_operator_ping(
        self,
        bot: Bot,
        chat_id: int,
        report: ProductionActivationReport,
    ) -> None:
        try:
            await bot.send_message(
                chat_id,
                "✅ <b>Newsroom operator online</b>\n"
                f"Bot: @{report.bot_username}\n"
                f"Channel: {report.channel.title if report.channel else 'n/a'}\n"
                "Use /startup_check · /production_ready",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("event=go_live_startup_ping_failed")

    async def _executive_dashboard_push(
        self,
        bot: Bot,
        chat_id: int,
        report: ProductionActivationReport,
    ) -> None:
        stage = self.first_publication.current()
        try:
            await bot.send_message(
                chat_id,
                "<b>Executive go-live dashboard</b>\n"
                f"Stage: <code>{stage.value}</code>\n"
                f"Rollout: <code>{self.first_publication.rollout_for()}</code>\n"
                f"Shadow: {'yes' if runtime_state.shadow_publish_only else 'no'}\n"
                f"Telegram: {'READY' if report.passed else 'BLOCKED'}\n"
                f"Next cmds: {self.first_publication.operator_commands_for_stage()}",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("event=go_live_dashboard_push_failed")

    async def _register_emergency_contacts(
        self,
        bot: Bot,
        operator_chat_id: int,
        contacts: frozenset[int],
    ) -> None:
        verified = [c for c in contacts if c in (self._last_activation.admin_ids_verified if self._last_activation else [])]
        fallback = len(contacts) >= 2
        try:
            await bot.send_message(
                operator_chat_id,
                "<b>Emergency contacts</b>\n"
                f"Registered: {len(contacts)} · verified: {len(verified)}\n"
                f"Multi-operator fallback: {'OK' if fallback else 'WARN — add 2+ admins'}",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("event=emergency_contact_notify_failed")

    def startup_check_text(self) -> str:
        r = self._last_activation
        if r is None:
            return "<b>Startup check</b>\nNo activation run yet — restart operator node."
        lines = [r.html_summary()]
        sig = self._signals_fn() if self._signals_fn else {}
        lines.append(f"\nQueue: {sig.get('queue_depth', '?')}")
        lines.append(f"Rollout env: {sig.get('rollout_stage', '?')}")
        return "\n".join(lines)

    def production_ready_text(self) -> str:
        r = self._last_activation
        sig = self._signals_fn() if self._signals_fn else {}
        blockers: list[str] = []
        if r is None or not r.passed:
            blockers.append("telegram_activation")
        from bot.go_live.first_publication import PublicationStage

        pub_stage = self.first_publication.current()
        if not runtime_state.shadow_publish_only and pub_stage in (
            PublicationStage.INTERNAL_SHADOW,
            PublicationStage.SHADOW_TRAFFIC,
        ):
            blockers.append("shadow_mode_required")
        if not sig.get("ga_ready", float(sig.get("go_live_confidence", 0)) >= 0.88):
            if float(sig.get("go_live_confidence", 0)) < 0.88:
                blockers.append("ga_confidence")
        if not sig.get("certified", False):
            blockers.append("certification")
        ready = not blockers and r is not None and r.passed
        lines = [
            f"<b>Production ready</b>: {'YES' if ready else 'NO'}",
            f"Stage: <code>{self.first_publication.current().value}</code>",
        ]
        if blockers:
            lines.append("Blockers: " + ", ".join(blockers))
        else:
            lines.append("Proceed: /activate_next_stage or env rollout promotion")
        return "\n".join(lines)

    def channel_status_text(self) -> str:
        r = self._last_activation
        if r is None or r.channel is None:
            return "<b>Channel status</b>\nRun startup to validate channel."
        c = r.channel
        lines = [
            "<b>Channel status</b>",
            f"{c.title} (<code>{c.chat_id}</code>)",
            f"Post: {'✓' if c.can_post_messages else '✗'}",
            f"Edit: {'✓' if c.can_edit_messages else '✗'}",
            f"Delete: {'✓' if c.can_delete_messages else '✗'}",
            f"Invite: {'✓' if c.can_invite_users else '✗'}",
            f"Manage: {'✓' if c.can_manage_chat else '✗'}",
        ]
        if c.linked_discussion_id:
            lines.append(f"Discussion: <code>{c.linked_discussion_id}</code>")
        return "\n".join(lines)
