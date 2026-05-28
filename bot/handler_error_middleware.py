"""Boundary middleware: handler failures must not kill the polling loop."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class SafeHandlerMiddleware(BaseMiddleware):
    """Catch message/update handler exceptions; reply to admin when possible."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            uid = None
            chat_id = None
            if isinstance(event, Message):
                uid = event.from_user.id if event.from_user else None
                chat_id = event.chat.id if event.chat else None
            elif isinstance(event, Update) and event.message:
                uid = event.message.from_user.id if event.message.from_user else None
                chat_id = event.message.chat.id if event.message.chat else None
            try:
                from utils.metrics import inc

                inc("bot_handler_errors_total")
            except Exception:
                pass
            log_event(
                logger,
                "GLOBAL_HANDLER_EXCEPTION_LOGGER",
                error=repr(exc)[:500],
                user_id=uid,
                chat_id=chat_id,
                event_type=type(event).__name__,
            )
            log_event(
                logger,
                "bot.handler.failed",
                error=repr(exc)[:500],
                user_id=uid,
                chat_id=chat_id,
                event_type=type(event).__name__,
            )
            logger.exception("handler failed")
            try:
                answer = getattr(event, "answer", None)
                if callable(answer):
                    await answer("Command failed — check server logs.")
            except Exception:
                pass
            return None
