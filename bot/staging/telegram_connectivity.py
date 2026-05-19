from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_SEC = 1.0


@dataclass
class ChannelCheck:
    name: str
    chat_id: int | None
    passed: bool
    detail: str
    can_post: bool = False


@dataclass
class TelegramConnectivityReport:
    bot_ok: bool
    bot_username: str | None
    checks: list[ChannelCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    inline_keyboard_ok: bool = False
    publish_probe_ok: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.bot_ok
            and all(c.passed for c in self.checks)
            and self.inline_keyboard_ok
        )

    def structured_diagnostics(self) -> dict[str, object]:
        return {
            "bot_ok": self.bot_ok,
            "bot_username": self.bot_username,
            "inline_keyboard_ok": self.inline_keyboard_ok,
            "publish_probe_ok": self.publish_probe_ok,
            "checks": [
                {
                    "name": c.name,
                    "chat_id": c.chat_id,
                    "passed": c.passed,
                    "can_post": c.can_post,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
            "errors": list(self.errors),
            "ready": self.passed,
        }

    def operator_summary(self) -> str:
        lines = ["Telegram staging connectivity:"]
        lines.append(f"  Bot: {'OK' if self.bot_ok else 'FAIL'} ({self.bot_username or 'unknown'})")
        for c in self.checks:
            mark = "OK" if c.passed else "FAIL"
            post = "can_post" if c.can_post else "no_post"
            lines.append(f"  [{mark}] {c.name} ({post}): {c.detail}")
        for err in self.errors:
            lines.append(f"  ERROR: {err}")
        lines.append(f"Overall: {'READY' if self.passed else 'NOT READY'}")
        return "\n".join(lines)


class TelegramConnectivityCheck:
    """Validate bot token, digest channel, and operator chat on startup."""

    def __init__(
        self,
        bot: Bot,
        *,
        digest_channel_id: int | None,
        operator_chat_id: int | None,
        publish_channel_id: int | None = None,
    ) -> None:
        self._bot = bot
        self._digest_id = digest_channel_id
        self._operator_id = operator_chat_id
        self._publish_id = publish_channel_id

    async def run(self, *, strict: bool = False) -> TelegramConnectivityReport:
        report = TelegramConnectivityReport(bot_ok=False, bot_username=None)
        report.bot_ok, report.bot_username = await self._verify_bot()
        if not report.bot_ok:
            report.errors.append("bot getMe failed")
            if strict:
                return report

        if self._digest_id is not None:
            report.checks.append(await self._check_channel("digest", self._digest_id, require_post=True))
        elif self._publish_id is not None:
            report.checks.append(await self._check_channel("publish", self._publish_id, require_post=True))
        else:
            report.checks.append(
                ChannelCheck("digest", None, False, "TELEGRAM_DIGEST_CHANNEL_ID or TELEGRAM_CHANNEL_ID unset")
            )

        if self._operator_id is not None:
            report.checks.append(await self._check_channel("operator", self._operator_id, require_post=False))
            report.inline_keyboard_ok = await self._probe_inline_keyboard(self._operator_id)
            if not report.inline_keyboard_ok:
                report.errors.append("inline keyboard probe failed on operator chat")
        else:
            report.checks.append(
                ChannelCheck("operator", None, False, "TELEGRAM_OPERATOR_CHAT_ID unset")
            )

        digest_id = self._digest_id or self._publish_id
        if digest_id is not None:
            report.publish_probe_ok = await self._probe_publish_permission(digest_id)

        logger.info(
            "event=telegram_startup_diagnostics %s",
            json.dumps(report.structured_diagnostics(), default=str),
        )

        if not report.passed:
            logger.error("event=telegram_connectivity_failed %s", report.operator_summary())
        else:
            logger.info("event=telegram_connectivity_ok username=%s", report.bot_username)
        return report

    async def _verify_bot(self) -> tuple[bool, str | None]:
        for attempt in range(_MAX_RETRIES):
            try:
                me = await self._bot.get_me()
                return True, me.username
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError as exc:
                logger.warning("event=telegram_get_me_failed attempt=%d error=%s", attempt, exc)
                await asyncio.sleep(_RETRY_BASE_SEC * (attempt + 1))
        return False, None

    async def _check_channel(
        self,
        name: str,
        chat_id: int,
        *,
        require_post: bool,
    ) -> ChannelCheck:
        for attempt in range(_MAX_RETRIES):
            try:
                chat = await self._bot.get_chat(chat_id)
                title = getattr(chat, "title", None) or getattr(chat, "username", str(chat_id))
                can_post = False
                if require_post:
                    me = await self._bot.get_me()
                    member = await self._bot.get_chat_member(chat_id, me.id)
                    status = member.status
                    can_post = status in (
                        ChatMemberStatus.ADMINISTRATOR,
                        ChatMemberStatus.CREATOR,
                    )
                    if status == ChatMemberStatus.ADMINISTRATOR and member.can_post_messages is False:
                        can_post = False
                    if not can_post:
                        return ChannelCheck(
                            name,
                            chat_id,
                            False,
                            f"connected to '{title}' but bot cannot post",
                            can_post=False,
                        )
                else:
                    can_post = True
                return ChannelCheck(
                    name,
                    chat_id,
                    True,
                    f"connected: {title}",
                    can_post=can_post,
                )
            except TelegramForbiddenError:
                return ChannelCheck(
                    name,
                    chat_id,
                    False,
                    "bot forbidden — add bot to chat with post rights",
                    can_post=False,
                )
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError as exc:
                logger.warning(
                    "event=telegram_channel_check_failed name=%s attempt=%d error=%s",
                    name,
                    attempt,
                    exc,
                )
                await asyncio.sleep(_RETRY_BASE_SEC * (attempt + 1))
        return ChannelCheck(name, chat_id, False, "max retries exceeded", can_post=False)

    async def _probe_inline_keyboard(self, chat_id: int) -> bool:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✓ startup",
                        callback_data="ops:startup_probe",
                    )
                ]
            ]
        )
        for attempt in range(_MAX_RETRIES):
            try:
                msg = await self._bot.send_message(
                    chat_id,
                    "[system] inline keyboard probe",
                    reply_markup=markup,
                    disable_notification=True,
                )
                try:
                    await self._bot.delete_message(chat_id, msg.message_id)
                except TelegramAPIError:
                    pass
                return True
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError as exc:
                logger.warning(
                    "event=inline_keyboard_probe_failed attempt=%d error=%s",
                    attempt,
                    exc,
                )
                await asyncio.sleep(_RETRY_BASE_SEC * (attempt + 1))
        return False

    async def _probe_publish_permission(self, channel_id: int) -> bool:
        for attempt in range(_MAX_RETRIES):
            try:
                msg = await self._bot.send_message(
                    channel_id,
                    "[system] publish permission probe",
                    disable_notification=True,
                )
                try:
                    await self._bot.delete_message(channel_id, msg.message_id)
                except TelegramAPIError:
                    pass
                return True
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except TelegramAPIError as exc:
                logger.warning(
                    "event=publish_probe_failed attempt=%d error=%s",
                    attempt,
                    exc,
                )
                await asyncio.sleep(_RETRY_BASE_SEC * (attempt + 1))
        return False
