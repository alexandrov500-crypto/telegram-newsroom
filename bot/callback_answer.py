"""Reliable answers to inline button presses (no stuck loading spinner)."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


def _already_answered(exc: TelegramBadRequest) -> bool:
    err = str(exc).lower()
    return (
        "query is too old" in err
        or "query id is invalid" in err
        or "response already" in err
        or "already" in err and "answer" in err
    )


async def callback_ack(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    """
    Acknowledge callback_query. If Telegram rejects a second answer, post text in chat.
    """
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        if _already_answered(exc):
            if text and callback.message is not None:
                prefix = "⚠️ " if show_alert else ""
                await callback.message.answer(f"{prefix}{text}"[:4096])
            return
        raise
