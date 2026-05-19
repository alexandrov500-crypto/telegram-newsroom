from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import ChatMemberAdministrator

logger = logging.getLogger(__name__)

_RETRY_MAX = 3
_RETRY_BASE = 1.0

REQUIRED_ADMIN_CAPABILITIES = (
    "can_post_messages",
    "can_edit_messages",
    "can_delete_messages",
    "can_invite_users",
    "can_manage_chat",
)


@dataclass(frozen=True)
class ChannelPermissions:
    chat_id: int
    title: str
    is_admin: bool
    can_post_messages: bool
    can_edit_messages: bool
    can_delete_messages: bool
    can_invite_users: bool
    can_manage_chat: bool
    linked_discussion_id: int | None = None

    @property
    def all_required(self) -> bool:
        return all(
            (
                self.is_admin,
                self.can_post_messages,
                self.can_edit_messages,
                self.can_delete_messages,
                self.can_invite_users,
                self.can_manage_chat,
            ),
        )

    def missing(self) -> list[str]:
        out: list[str] = []
        if not self.is_admin:
            out.append("not_admin")
        for cap in REQUIRED_ADMIN_CAPABILITIES:
            if not getattr(self, cap, False):
                out.append(cap)
        return out


@dataclass
class ProductionActivationReport:
    bot_ok: bool
    bot_username: str | None
    channel: ChannelPermissions | None = None
    operator_chat_ok: bool = False
    admin_ids_verified: list[int] = field(default_factory=list)
    shadow_mode_ok: bool = False
    publish_probe_ok: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.bot_ok
            and self.channel is not None
            and self.channel.all_required
            and self.operator_chat_ok
            and len(self.admin_ids_verified) > 0
            and self.publish_probe_ok
        )

    def structured(self) -> dict[str, object]:
        return {
            "bot_ok": self.bot_ok,
            "bot_username": self.bot_username,
            "channel": (
                {
                    "chat_id": self.channel.chat_id,
                    "title": self.channel.title,
                    "permissions": {
                        c: getattr(self.channel, c) for c in REQUIRED_ADMIN_CAPABILITIES
                    },
                    "linked_discussion_id": self.channel.linked_discussion_id,
                    "missing": self.channel.missing(),
                }
                if self.channel
                else None
            ),
            "operator_chat_ok": self.operator_chat_ok,
            "admin_ids_verified": self.admin_ids_verified,
            "shadow_mode_ok": self.shadow_mode_ok,
            "publish_probe_ok": self.publish_probe_ok,
            "errors": self.errors,
            "ready": self.passed,
        }

    def html_summary(self) -> str:
        lines = ["<b>Telegram production activation</b>"]
        lines.append(f"Bot: {'✓' if self.bot_ok else '✗'} @{self.bot_username or '?'}")
        if self.channel:
            mark = "✓" if self.channel.all_required else "✗"
            lines.append(f"Channel {mark}: {self.channel.title}")
            missing = self.channel.missing()
            if missing:
                lines.append(f"Missing: {', '.join(missing)}")
            if self.channel.linked_discussion_id:
                lines.append(f"Discussion group: {self.channel.linked_discussion_id}")
        lines.append(f"Operator chat: {'✓' if self.operator_chat_ok else '✗'}")
        lines.append(f"Admins verified: {len(self.admin_ids_verified)}")
        lines.append(f"Publish probe: {'✓' if self.publish_probe_ok else '✗'}")
        lines.append(f"Shadow validated: {'✓' if self.shadow_mode_ok else '✗'}")
        for e in self.errors[:5]:
            lines.append(f"⚠ {e}")
        lines.append(f"\n<b>{'READY' if self.passed else 'NOT READY'}</b>")
        return "\n".join(lines)


class ProductionTelegramActivation:
    """Hard-fail channel permission validation for public go-live."""

    def __init__(
        self,
        bot: Bot,
        *,
        channel_id: int,
        operator_chat_id: int | None,
        admin_user_ids: frozenset[int],
        strict_permissions: bool = True,
        run_publish_probe: bool = True,
    ) -> None:
        self._bot = bot
        self._channel_id = channel_id
        self._operator_id = operator_chat_id
        self._admin_ids = admin_user_ids
        self._strict = strict_permissions
        self._run_probe = run_publish_probe

    async def run(
        self,
        *,
        shadow_publish_only: bool,
    ) -> ProductionActivationReport:
        report = ProductionActivationReport(bot_ok=False, bot_username=None)
        report.bot_ok, report.bot_username = await self._get_me()
        if not report.bot_ok:
            report.errors.append("getMe failed")
            return report

        report.channel = await self._validate_channel_permissions(self._channel_id)
        if report.channel is None:
            report.errors.append("channel unreachable")
        elif self._strict and not report.channel.all_required:
            report.errors.append(
                f"insufficient permissions: {', '.join(report.channel.missing())}",
            )

        if self._operator_id is not None:
            report.operator_chat_ok = await self._probe_operator_chat(self._operator_id)
            if not report.operator_chat_ok:
                report.errors.append("operator chat unreachable")
        else:
            report.errors.append("TELEGRAM_OPERATOR_CHAT_ID unset")

        report.admin_ids_verified = await self._verify_admin_ids()
        if not report.admin_ids_verified:
            report.errors.append("no admin user IDs verified via getChat")

        report.shadow_mode_ok = shadow_publish_only or not self._strict
        if self._strict and not shadow_publish_only:
            report.shadow_mode_ok = False
            report.errors.append("shadow_publish_only must be true before first public launch")

        if self._run_probe:
            report.publish_probe_ok = await self._publish_probe(self._channel_id)
            if not report.publish_probe_ok:
                report.errors.append("startup publish probe failed")

        logger.info(
            "event=production_telegram_activation %s",
            json.dumps(report.structured(), default=str),
        )
        return report

    async def _get_me(self) -> tuple[bool, str | None]:
        for attempt in range(_RETRY_MAX):
            try:
                me = await self._bot.get_me()
                return True, me.username
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError:
                await asyncio.sleep(_RETRY_BASE * (attempt + 1))
        return False, None

    async def _validate_channel_permissions(self, chat_id: int) -> ChannelPermissions | None:
        for attempt in range(_RETRY_MAX):
            try:
                chat = await self._bot.get_chat(chat_id)
                title = getattr(chat, "title", None) or str(chat_id)
                linked = getattr(chat, "linked_chat_id", None)
                me = await self._bot.get_me()
                member = await self._bot.get_chat_member(chat_id, me.id)
                if member.status == ChatMemberStatus.CREATOR:
                    return ChannelPermissions(
                        chat_id=chat_id,
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
                        chat_id=chat_id,
                        title=title,
                        is_admin=False,
                        can_post_messages=False,
                        can_edit_messages=False,
                        can_delete_messages=False,
                        can_invite_users=False,
                        can_manage_chat=False,
                        linked_discussion_id=linked,
                    )
                admin = member
                if isinstance(admin, ChatMemberAdministrator):
                    return ChannelPermissions(
                        chat_id=chat_id,
                        title=title,
                        is_admin=True,
                        can_post_messages=bool(admin.can_post_messages),
                        can_edit_messages=bool(admin.can_edit_messages),
                        can_delete_messages=bool(admin.can_delete_messages),
                        can_invite_users=bool(admin.can_invite_users),
                        can_manage_chat=bool(admin.can_manage_chat),
                        linked_discussion_id=linked,
                    )
            except TelegramForbiddenError:
                return None
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError:
                await asyncio.sleep(_RETRY_BASE * (attempt + 1))
        return None

    async def _probe_operator_chat(self, chat_id: int) -> bool:
        try:
            await self._bot.send_message(
                chat_id,
                "[system] operator startup probe",
                disable_notification=True,
            )
            return True
        except TelegramAPIError:
            return False

    async def _verify_admin_ids(self) -> list[int]:
        verified: list[int] = []
        for uid in self._admin_ids:
            try:
                await self._bot.get_chat(uid)
                verified.append(uid)
            except TelegramAPIError:
                continue
        return verified

    async def _publish_probe(self, channel_id: int) -> bool:
        for attempt in range(_RETRY_MAX):
            try:
                msg = await self._bot.send_message(
                    channel_id,
                    "[system] production startup publish test",
                    disable_notification=True,
                )
                try:
                    await self._bot.delete_message(channel_id, msg.message_id)
                except TelegramAPIError:
                    pass
                return True
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError:
                await asyncio.sleep(_RETRY_BASE * (attempt + 1))
        return False
