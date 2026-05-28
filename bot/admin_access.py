"""Operator access checks for admin bot commands and inline keyboards."""

from __future__ import annotations

from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, User

from app.config import Settings


def is_admin_user(user: User | None, settings: Settings) -> bool:
    if user is None:
        return False
    return int(user.id) in settings.admin_user_ids


def _chat_allowed(chat_type: ChatType, chat_id: int, settings: Settings) -> bool:
    if chat_type == ChatType.PRIVATE:
        return True
    mod = settings.moderation_chat_id
    if mod is not None and int(chat_id) == int(mod):
        return True
    return False


def can_handle_admin_callback(callback: CallbackQuery, settings: Settings) -> bool:
    """True when an admin may use draft moderation inline buttons."""
    if not is_admin_user(callback.from_user, settings):
        return False
    msg = callback.message
    if msg is None:
        return False
    return _chat_allowed(msg.chat.type, int(msg.chat.id), settings)


def can_handle_admin_message(message: Message, settings: Settings) -> bool:
    if not is_admin_user(message.from_user, settings):
        return False
    return _chat_allowed(message.chat.type, int(message.chat.id), settings)
