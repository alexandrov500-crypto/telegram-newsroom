"""Telegram Bot API send kwargs — method-specific whitelists only.

``disable_web_page_preview`` / ``link_preview_options`` are valid for ``send_message`` only,
not for send_photo, send_video, send_document, send_animation, or send_media_group.
"""

from __future__ import annotations

import logging
import os
from typing import Any, TYPE_CHECKING

from aiogram.enums import ParseMode

from utils.structured_log import log_event

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import FSInputFile, InlineKeyboardMarkup, InputFileUnion, ReplyParameters, URLInputFile

logger = logging.getLogger(__name__)

# Params that must never appear on media/document sends (Telegram sendMessage-only).
_MESSAGE_ONLY_KWARGS = frozenset({"disable_web_page_preview", "link_preview_options"})

_MOCK_PUBLISH_SEQ = 900_000_000


def _staging_mock_telegram_enabled() -> bool:
    return os.getenv("STAGING_MOCK_TELEGRAM_PUBLISH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _next_mock_message_id() -> int:
    global _MOCK_PUBLISH_SEQ
    _MOCK_PUBLISH_SEQ += 1
    return _MOCK_PUBLISH_SEQ

def _drop_message_only(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if k not in _MESSAGE_ONLY_KWARGS}


def guard_media_kwargs(
    kwargs: dict[str, Any],
    *,
    transport_method: str,
    draft_id: int | None = None,
) -> dict[str, Any]:
    """Fail-closed: forbidden sendMessage-only keys must never reach Bot.send_* media methods."""
    from publisher.telegram_forensic import assert_media_kwargs_fail_closed

    assert_media_kwargs_fail_closed(
        kwargs,
        transport_method=transport_method,
        caller_module=__file__,
        draft_id=draft_id,
    )
    return kwargs


def kwargs_keys_for_log(kwargs: dict[str, Any]) -> list[str]:
    return sorted(kwargs.keys())


def log_transport_send(
    *,
    transport_method: str,
    kwargs_used: dict[str, Any],
    draft_id: int | None = None,
    publish_attempt: int | None = None,
    channel_id: int | None = None,
) -> None:
    fields: dict[str, Any] = {
        "transport_method": transport_method,
        "kwargs_keys": kwargs_keys_for_log(kwargs_used),
    }
    if draft_id is not None:
        fields["draft_id"] = draft_id
    if publish_attempt is not None:
        fields["publish_attempt"] = int(publish_attempt)
    if channel_id is not None:
        fields["channel_id"] = channel_id
    log_event(logger, "publish.transport_send", **fields)


def message_send_kwargs(
    *,
    chat_id: int,
    parse_mode: ParseMode = ParseMode.HTML,
    disable_web_page_preview: bool = True,
    disable_notification: bool = False,
    protect_content: bool = False,
    reply_markup: Any = None,
    reply_parameters: ReplyParameters | None = None,
    message_thread_id: int | None = None,
) -> dict[str, Any]:
    """Kwargs for ``Bot.send_message`` (link preview flags allowed)."""
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
        "disable_notification": disable_notification,
    }
    if protect_content:
        kwargs["protect_content"] = True
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    if reply_parameters is not None:
        kwargs["reply_parameters"] = reply_parameters
    if message_thread_id is not None:
        kwargs["message_thread_id"] = message_thread_id
    return kwargs


def photo_send_kwargs(
    *,
    chat_id: int,
    caption: str | None = None,
    parse_mode: ParseMode = ParseMode.HTML,
    disable_notification: bool = False,
    protect_content: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
    reply_parameters: ReplyParameters | None = None,
    has_spoiler: bool = False,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }
    if caption:
        kwargs["caption"] = caption
    if protect_content:
        kwargs["protect_content"] = True
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    if reply_parameters is not None:
        kwargs["reply_parameters"] = reply_parameters
    if has_spoiler:
        kwargs["has_spoiler"] = True
    return _drop_message_only(kwargs)


def video_send_kwargs(
    *,
    chat_id: int,
    caption: str | None = None,
    parse_mode: ParseMode = ParseMode.HTML,
    disable_notification: bool = False,
    protect_content: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
    reply_parameters: ReplyParameters | None = None,
    thumbnail: URLInputFile | None = None,
    has_spoiler: bool = False,
    width: int | None = None,
    height: int | None = None,
    duration: int | None = None,
    supports_streaming: bool = True,
) -> dict[str, Any]:
    kwargs = photo_send_kwargs(
        chat_id=chat_id,
        caption=caption,
        parse_mode=parse_mode,
        disable_notification=disable_notification,
        protect_content=protect_content,
        reply_markup=reply_markup,
        reply_parameters=reply_parameters,
        has_spoiler=has_spoiler,
    )
    if thumbnail is not None:
        kwargs["thumbnail"] = thumbnail
    if width is not None:
        kwargs["width"] = int(width)
    if height is not None:
        kwargs["height"] = int(height)
    if duration is not None:
        kwargs["duration"] = int(duration)
    if supports_streaming:
        kwargs["supports_streaming"] = True
    return _drop_message_only(kwargs)


async def send_channel_message(
    bot: Bot,
    *,
    text: str,
    chat_id: int,
    draft_id: int | None = None,
    publish_attempt: int | None = None,
    disable_web_page_preview: bool = True,
    disable_notification: bool = False,
) -> int:
    kwargs = message_send_kwargs(
        chat_id=chat_id,
        disable_web_page_preview=disable_web_page_preview,
        disable_notification=disable_notification,
    )
    log_transport_send(
        transport_method="send_message",
        kwargs_used=kwargs,
        draft_id=draft_id,
        publish_attempt=publish_attempt,
        channel_id=chat_id,
    )
    if _staging_mock_telegram_enabled():
        log_event(logger, "publish.transport_mock", transport_method="send_message", draft_id=draft_id)
        return _next_mock_message_id()
    msg = await bot.send_message(text=text, **kwargs)
    return int(msg.message_id)


async def send_channel_photo(
    bot: Bot,
    *,
    photo: FSInputFile | URLInputFile,
    chat_id: int,
    caption: str | None = None,
    draft_id: int | None = None,
    publish_attempt: int | None = None,
    disable_notification: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int:
    kwargs = guard_media_kwargs(
        photo_send_kwargs(
            chat_id=chat_id,
            caption=caption,
            disable_notification=disable_notification,
            reply_markup=reply_markup,
        ),
        transport_method="send_photo",
        draft_id=draft_id,
    )
    log_transport_send(
        transport_method="send_photo",
        kwargs_used=kwargs,
        draft_id=draft_id,
        publish_attempt=publish_attempt,
        channel_id=chat_id,
    )
    if _staging_mock_telegram_enabled():
        log_event(logger, "publish.transport_mock", transport_method="send_photo", draft_id=draft_id)
        return _next_mock_message_id()
    msg = await bot.send_photo(photo=photo, **kwargs)
    return int(msg.message_id)


async def send_channel_video(
    bot: Bot,
    *,
    video: FSInputFile | URLInputFile,
    chat_id: int,
    caption: str | None = None,
    draft_id: int | None = None,
    publish_attempt: int | None = None,
    disable_notification: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
    thumbnail: URLInputFile | None = None,
    width: int | None = None,
    height: int | None = None,
    duration: int | None = None,
) -> int:
    kwargs = guard_media_kwargs(
        video_send_kwargs(
            chat_id=chat_id,
            caption=caption,
            disable_notification=disable_notification,
            reply_markup=reply_markup,
            thumbnail=thumbnail,
            width=width,
            height=height,
            duration=duration,
        ),
        transport_method="send_video",
        draft_id=draft_id,
    )
    log_transport_send(
        transport_method="send_video",
        kwargs_used=kwargs,
        draft_id=draft_id,
        publish_attempt=publish_attempt,
        channel_id=chat_id,
    )
    if _staging_mock_telegram_enabled():
        log_event(logger, "publish.transport_mock", transport_method="send_video", draft_id=draft_id)
        return _next_mock_message_id()
    msg = await bot.send_video(video=video, **kwargs)
    return int(msg.message_id)


# Stable names for transport layer documentation / imports
build_message_kwargs = message_send_kwargs
build_photo_kwargs = photo_send_kwargs
build_video_kwargs = video_send_kwargs

# Install Bot.send_* forensic guards when transport layer loads (idempotent).
try:
    from publisher.telegram_forensic import install_media_send_forensic_guards

    install_media_send_forensic_guards()
except Exception:
    pass
