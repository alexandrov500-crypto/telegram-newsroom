from __future__ import annotations

import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import ChatMemberAdministrator, User

from bot.go_live.telegram_activation import ChannelPermissions

logger = logging.getLogger(__name__)


@dataclass
class PreflightLine:
    label: str
    ok: bool
    reason: str = ""

    def format(self) -> str:
        mark = "OK" if self.ok else "FAIL"
        line = f"[{mark}] {self.label}"
        if not self.ok and self.reason:
            line += f"\n      Reason: {self.reason}"
        return line


@dataclass
class PilotPreflightReport:
    lines: list[PreflightLine] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(ln.ok for ln in self.lines)

    def add(self, label: str, ok: bool, reason: str = "") -> None:
        self.lines.append(PreflightLine(label, ok, reason))

    def render(self) -> str:
        out = ["=" * 48, "CONTROLLED PUBLIC PILOT — PREFLIGHT", "=" * 48, ""]
        for ln in self.lines:
            out.append(ln.format())
        out.append("")
        if self.passed:
            out.append("PILOT STATUS: READY")
        else:
            out.append("PILOT STATUS: NOT READY")
            out.append("Rule: freeze first · analyze second · resume later")
        out.append("=" * 48)
        return "\n".join(out)


async def authenticate_bot(token: str) -> User:
    """Validate BOT_TOKEN; raises on failure."""
    bot = Bot(token=token, default=DefaultBotProperties())
    try:
        me = await bot.get_me()
        logger.info(
            "event=telegram_bot_authenticated username=%s bot_id=%s",
            me.username,
            me.id,
        )
        return me
    except TelegramAPIError as exc:
        logger.error("event=telegram_bot_auth_failed error=%s", exc)
        raise RuntimeError(f"Invalid BOT_TOKEN: {exc}") from exc
    finally:
        await bot.session.close()


async def authenticate_bot_instance(bot: Bot) -> User:
    """Log bot identity at operator startup; raises on invalid token."""
    try:
        me = await bot.get_me()
    except TelegramAPIError as exc:
        logger.error("event=telegram_bot_auth_failed error=%s", exc)
        raise RuntimeError(f"Invalid BOT_TOKEN: {exc}") from exc
    logger.info(
        "event=telegram_bot_authenticated username=%s bot_id=%s",
        me.username,
        me.id,
    )
    return me


async def fetch_channel_permissions(bot: Bot, channel_id: int) -> ChannelPermissions | None:
    try:
        chat = await bot.get_chat(channel_id)
        title = getattr(chat, "title", None) or str(channel_id)
        linked = getattr(chat, "linked_chat_id", None)
        me = await bot.get_me()
        member = await bot.get_chat_member(channel_id, me.id)
        if member.status == ChatMemberStatus.CREATOR:
            return ChannelPermissions(
                chat_id=channel_id,
                title=title,
                is_admin=True,
                can_post_messages=True,
                can_edit_messages=True,
                can_delete_messages=True,
                can_invite_users=True,
                can_manage_chat=True,
                linked_discussion_id=linked,
            )
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return ChannelPermissions(
                chat_id=channel_id,
                title=title,
                is_admin=False,
                can_post_messages=False,
                can_edit_messages=False,
                can_delete_messages=False,
                can_invite_users=False,
                can_manage_chat=False,
                linked_discussion_id=linked,
            )
        if isinstance(member, ChatMemberAdministrator):
            return ChannelPermissions(
                chat_id=channel_id,
                title=title,
                is_admin=True,
                can_post_messages=bool(member.can_post_messages),
                can_edit_messages=bool(member.can_edit_messages),
                can_delete_messages=bool(member.can_delete_messages),
                can_invite_users=bool(member.can_invite_users),
                can_manage_chat=bool(member.can_manage_chat),
                linked_discussion_id=linked,
            )
    except TelegramForbiddenError:
        return None
    except TelegramAPIError:
        return None
    return None


async def validate_public_channel(bot: Bot, channel_id: int) -> PreflightLine:
    perms = await fetch_channel_permissions(bot, channel_id)
    if perms is None:
        return PreflightLine(
            "Public channel accessible",
            False,
            "Bot cannot access channel — add bot as admin",
        )
    missing: list[str] = []
    if not perms.can_post_messages:
        missing.append("post_messages (includes media)")
    if not perms.can_edit_messages:
        missing.append("edit_messages")
    if not perms.can_delete_messages:
        missing.append("delete_messages")
    if missing:
        return PreflightLine(
            "Public channel accessible (post/edit/delete/media)",
            False,
            f"Missing permissions: {', '.join(missing)}",
        )
    return PreflightLine(
        "Public channel accessible (post/edit/delete/media)",
        True,
        perms.title,
    )


async def validate_send_channel(
    bot: Bot,
    channel_id: int,
    *,
    label: str,
    probe_send: bool = True,
) -> PreflightLine:
    perms = await fetch_channel_permissions(bot, channel_id)
    if perms is None:
        try:
            await bot.get_chat(channel_id)
        except TelegramAPIError as exc:
            return PreflightLine(
                label,
                False,
                f"Cannot access channel: {exc}",
            )
    if probe_send:
        try:
            await bot.send_message(
                channel_id,
                "[pilot preflight] connectivity check",
                disable_notification=True,
            )
            return PreflightLine(label, True, "send OK")
        except TelegramAPIError as exc:
            return PreflightLine(label, False, str(exc)[:120])
    return PreflightLine(label, True, "reachable")


async def send_test_messages(
    bot: Bot,
    *,
    ops_channel_id: int,
    shadow_channel_id: int | None,
) -> list[PreflightLine]:
    results: list[PreflightLine] = []
    if shadow_channel_id:
        try:
            msg = await bot.send_message(
                shadow_channel_id,
                "<b>Pilot preflight</b> shadow channel test ✓",
                parse_mode="HTML",
                disable_notification=True,
            )
            try:
                await bot.delete_message(shadow_channel_id, msg.message_id)
            except TelegramAPIError:
                pass
            results.append(PreflightLine("Shadow test message", True, "sent and cleaned"))
        except TelegramAPIError as exc:
            results.append(PreflightLine("Shadow test message", False, str(exc)[:120]))
    if ops_channel_id:
        try:
            await bot.send_message(
                ops_channel_id,
                "[pilot] ops channel connectivity OK",
                disable_notification=True,
            )
            results.append(PreflightLine("Ops startup test message", True, "sent"))
        except TelegramAPIError as exc:
            results.append(PreflightLine("Ops startup test message", False, str(exc)[:120]))
    return results


def pilot_startup_banner_text() -> str:
    import os

    from bot.runtime.instance import get_runtime_identity

    ident = get_runtime_identity()
    instance_line = ident.log_line() if ident else "Runtime instance: (pending)"
    profile = ident.runtime_profile if ident else os.getenv("RUNTIME_PROFILE", "canary")
    return (
        "🟢 <b>CONTROLLED PUBLIC PILOT ACTIVE</b>\n\n"
        f"<code>{instance_line}</code>\n"
        f"Profile: <code>{profile}</code>\n"
        f"Mode: <code>{os.getenv('LIVE_MODE', 'canary')}</code>\n"
        f"Max posts/hour: {os.getenv('LIVE_CANARY_MAX_PER_HOUR', '3')}\n"
        f"Approval required: {os.getenv('LIVE_SUPERVISED_APPROVAL', 'true')}\n"
        f"Rollback enabled: {os.getenv('LIVE_ENABLE_ROLLBACK', 'true')}\n"
        f"Freeze-on-anomaly: {os.getenv('LIVE_FREEZE_ON_ANOMALY', 'true')}\n\n"
        "Pilot started successfully."
    )


async def send_pilot_startup_banner(bot: Bot, ops_channel_id: int) -> bool:
    try:
        await bot.send_message(
            ops_channel_id,
            pilot_startup_banner_text(),
            parse_mode="HTML",
            disable_notification=True,
        )
        logger.info("event=pilot_startup_banner_sent channel_id=%s", ops_channel_id)
        return True
    except TelegramAPIError as exc:
        logger.warning("event=pilot_startup_banner_failed error=%s", exc)
        return False


async def simulate_operational_commands(db_path) -> list[PreflightLine]:
    """Exercise freeze/resume/live_status without Telegram."""
    from pathlib import Path

    from bot.live_ops.controlled_factory import build_controlled_live_stack

    lines: list[PreflightLine] = []
    try:
        coord = build_controlled_live_stack(Path(db_path))
        await coord.startup()
        status = coord.repository.get_state() or {}
        lines.append(
            PreflightLine(
                "/live_status simulation",
                bool(status.get("live_mode")),
                f"mode={status.get('live_mode')}",
            ),
        )
        coord.override.pause_live()
        paused = bool((coord.repository.get_state() or {}).get("paused"))
        lines.append(
            PreflightLine("/freeze_publishing simulation", paused, "paused=1"),
        )
        coord.override.resume_live()
        resumed = not bool((coord.repository.get_state() or {}).get("paused"))
        lines.append(
            PreflightLine("/resume_live simulation", resumed, "paused=0"),
        )
    except Exception as exc:
        lines.append(
            PreflightLine("Operational commands simulation", False, str(exc)[:120]),
        )
    return lines
