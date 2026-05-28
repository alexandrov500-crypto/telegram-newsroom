from __future__ import annotations

from unittest.mock import MagicMock

from aiogram.enums import ChatType

from bot.admin_access import can_handle_admin_callback, can_handle_admin_message
from tests.conftest import minimal_test_settings


def _callback(*, user_id: int, chat_id: int, chat_type: ChatType = ChatType.PRIVATE):
    cb = MagicMock()
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.message = MagicMock()
    cb.message.chat = MagicMock()
    cb.message.chat.id = chat_id
    cb.message.chat.type = chat_type
    return cb


def test_admin_callback_private_by_user_id() -> None:
    settings = minimal_test_settings(admin_user_id=167395657, admin_user_ids=frozenset({167395657}))
    cb = _callback(user_id=167395657, chat_id=999999)
    assert can_handle_admin_callback(cb, settings) is True


def test_admin_callback_denied_wrong_user() -> None:
    settings = minimal_test_settings(admin_user_ids=frozenset({1}))
    cb = _callback(user_id=2, chat_id=2)
    assert can_handle_admin_callback(cb, settings) is False


def test_admin_callback_moderation_group() -> None:
    settings = minimal_test_settings(
        admin_user_ids=frozenset({42}),
        moderation_chat_id=-100555,
    )
    cb = _callback(user_id=42, chat_id=-100555, chat_type=ChatType.SUPERGROUP)
    assert can_handle_admin_callback(cb, settings) is True


def test_admin_message_private() -> None:
    settings = minimal_test_settings(admin_user_ids=frozenset({7}))
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = 7
    msg.chat = MagicMock()
    msg.chat.id = 7
    msg.chat.type = ChatType.PRIVATE
    assert can_handle_admin_message(msg, settings) is True
