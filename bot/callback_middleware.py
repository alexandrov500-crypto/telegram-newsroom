"""Middleware: log callbacks, answer on handler failure (avoids stuck loading spinner)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, TelegramObject

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class SafeCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        log_event(
            logger,
            "bot.callback.received",
            data=(event.data or "")[:64],
            user_id=event.from_user.id if event.from_user else None,
            chat_id=event.message.chat.id if event.message else None,
        )
        try:
            await event.answer()
        except TelegramBadRequest as exc:
            if "query is too old" not in str(exc).lower():
                logger.debug("callback early answer skipped: %s", exc)
        try:
            return await handler(event, data)
        except Exception as exc:
            try:
                from utils.metrics import inc

                inc("bot_handler_errors_total")
            except Exception:
                pass
            logger.exception("callback handler failed data=%s", event.data)
            try:
                if event.message is not None:
                    await event.message.answer("Action failed — see server logs")
            except Exception:
                pass
            return None
