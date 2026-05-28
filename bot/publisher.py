from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import FSInputFile, URLInputFile

from bot.editorial.formatting import (
    TELEGRAM_CAPTION_MAX,
    format_publish_caption,
    format_publish_message,
    truncate_html_safe,
)
from bot.processing.media import MEDIA_NONE, MEDIA_PHOTO, MEDIA_VIDEO, MediaInfo
from publisher.telegram_transport import message_send_kwargs

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_DELAY_SEC = 0.5


@dataclass(frozen=True, slots=True)
class PublishResult:
    success: bool
    duration_ms: int
    channel_id: int | None
    message_id: int | None = None
    error: str | None = None
    used_media: bool = False
    media_fallback: bool = False


def _log_publish(event: str, **fields: object) -> None:
    payload = " ".join(f"{key}={fields[key]!r}" for key in sorted(fields))
    logger.info("event=%s %s", event, payload)


def _resolve_media_input(media_url: str):
    if media_url.startswith("local://"):
        path = Path(media_url.removeprefix("local://"))
        if path.is_file():
            return FSInputFile(path)
        return None
    return URLInputFile(media_url)


class ChannelPublisher:
    """Publish text or rich media to the configured newsroom Telegram channel."""

    def __init__(self, bot: Bot, channel_id: int | None) -> None:
        self._bot = bot
        self._channel_id = channel_id

    @property
    def channel_configured(self) -> bool:
        return self._channel_id is not None

    @property
    def channel_id(self) -> int | None:
        return self._channel_id

    def _failure(
        self,
        *,
        channel_id: int | None,
        started: float,
        error: str,
        used_media: bool = False,
        media_fallback: bool = False,
    ) -> PublishResult:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _log_publish(
            "publish_failed",
            channel_id=channel_id,
            duration_ms=duration_ms,
            error=error,
        )
        return PublishResult(
            success=False,
            duration_ms=duration_ms,
            channel_id=channel_id,
            error=error,
            used_media=used_media,
            media_fallback=media_fallback,
        )

    def _classify_error(self, exc: TelegramAPIError) -> str:
        if isinstance(exc, TelegramForbiddenError):
            return (
                "Bot lacks permission to post in this channel "
                "(add bot as channel admin with post permission)"
            )
        if isinstance(exc, TelegramBadRequest):
            text = str(exc).lower()
            if "chat not found" in text:
                return "Channel not found; check TELEGRAM_CHANNEL_ID"
            if "not enough rights" in text or "have no rights" in text:
                return "Insufficient channel rights for this bot"
        return str(exc)

    async def _send_text_once(
        self,
        text: str,
        *,
        disable_notification: bool,
        channel_id: int | None = None,
    ) -> int:
        chat_id = channel_id if channel_id is not None else self._channel_id
        assert chat_id is not None
        kwargs = message_send_kwargs(
            chat_id=chat_id,
            disable_web_page_preview=False,
            disable_notification=disable_notification,
        )
        message = await self._bot.send_message(text=text, **kwargs)
        return message.message_id

    async def _send_media_once(
        self,
        *,
        media_type: str,
        media_url: str,
        caption: str,
        thumbnail_url: str | None,
        disable_notification: bool,
        channel_id: int | None = None,
    ) -> int:
        chat_id = channel_id if channel_id is not None else self._channel_id
        assert chat_id is not None
        media_input = _resolve_media_input(media_url)
        if media_input is None:
            raise ValueError("media_unavailable")

        from publisher.telegram_transport import send_channel_photo, send_channel_video

        if media_type == MEDIA_PHOTO:
            return await send_channel_photo(
                self._bot,
                photo=media_input,
                chat_id=int(chat_id),
                caption=caption,
                disable_notification=disable_notification,
            )
        if media_type == MEDIA_VIDEO:
            thumb = URLInputFile(thumbnail_url) if thumbnail_url and thumbnail_url.startswith("http") else None
            return await send_channel_video(
                self._bot,
                video=media_input,
                chat_id=int(chat_id),
                caption=caption,
                disable_notification=disable_notification,
                thumbnail=thumb,
            )
        raise ValueError(f"unsupported_media_type:{media_type}")

    async def publish_news(
        self,
        *,
        title: str,
        summary: str | None,
        link: str,
        tags: list[str] | None = None,
        source: str | None = None,
        media_type: str = MEDIA_NONE,
        media_url: str | None = None,
        thumbnail_url: str | None = None,
        trending_entities: list[str] | None = None,
        hook_line: str | None = None,
        original_title: str | None = None,
        show_original_subtitle: bool = False,
        disable_notification: bool = False,
        channel_id: int | None = None,
    ) -> PublishResult:
        """Publish with photo/video when available; fallback to text. Never raises."""
        target_channel = channel_id if channel_id is not None else self._channel_id
        caption = format_publish_caption(
            title=title,
            summary=summary or "",
            link=link,
            tags=tags or [],
            source=source,
            trending_entities=trending_entities,
            hook_line=hook_line,
            original_title=original_title,
            show_original_subtitle=show_original_subtitle,
        )
        text_body = format_publish_message(
            title=title,
            summary=summary or "",
            link=link,
            tags=tags or [],
            source=source,
            trending_entities=trending_entities,
            hook_line=hook_line,
            original_title=original_title,
            show_original_subtitle=show_original_subtitle,
        )
        has_media = (
            media_type in (MEDIA_PHOTO, MEDIA_VIDEO)
            and media_url
            and (media_url.startswith("http") or media_url.startswith("local://"))
        )
        if has_media:
            result = await self._publish_with_retries(
                media_type=media_type,
                media_url=str(media_url),
                caption=caption,
                thumbnail_url=thumbnail_url,
                disable_notification=disable_notification,
                channel_id=target_channel,
            )
            if result.success:
                logger.info(
                    "event=media_publish_success type=%s channel_id=%s message_id=%s",
                    media_type,
                    result.channel_id,
                    result.message_id,
                )
                return result
            logger.warning(
                "event=media_publish_failed type=%s error=%r",
                media_type,
                result.error,
            )
            logger.info("event=media_fallback_text channel_id=%s", target_channel)
            fallback = await self.send_to_channel(
                text_body,
                disable_notification=disable_notification,
                channel_id=target_channel,
            )
            return PublishResult(
                success=fallback.success,
                duration_ms=fallback.duration_ms,
                channel_id=fallback.channel_id,
                message_id=fallback.message_id,
                error=fallback.error,
                used_media=False,
                media_fallback=True,
            )

        return await self.send_to_channel(
            text_body,
            disable_notification=disable_notification,
            channel_id=target_channel,
        )

    async def publish_digest(
        self,
        content: str,
        *,
        hero: MediaInfo | None = None,
        disable_notification: bool = False,
        channel_id: int | None = None,
    ) -> PublishResult:
        """Publish digest with optional hero media; fallback to text-only."""
        target_channel = channel_id if channel_id is not None else self._channel_id
        if hero is not None and hero.has_media and hero.media_url:
            media_type = hero.media_type
            if media_type in (MEDIA_PHOTO, MEDIA_VIDEO):
                caption = truncate_html_safe(content, TELEGRAM_CAPTION_MAX)
                result = await self._publish_with_retries(
                    media_type=media_type,
                    media_url=str(hero.media_url),
                    caption=caption,
                    thumbnail_url=hero.thumbnail_url,
                    disable_notification=disable_notification,
                    channel_id=target_channel,
                )
                if result.success:
                    logger.info(
                        "event=media_publish_success type=%s digest=true message_id=%s",
                        media_type,
                        result.message_id,
                    )
                    return result
                logger.warning(
                    "event=media_publish_failed digest=true type=%s error=%r",
                    media_type,
                    result.error,
                )
                logger.info(
                    "event=media_fallback_text digest=true channel_id=%s",
                    target_channel,
                )
        return await self.send_to_channel(
            content,
            disable_notification=disable_notification,
            channel_id=target_channel,
        )

    async def _publish_with_retries(
        self,
        *,
        media_type: str,
        media_url: str,
        caption: str,
        thumbnail_url: str | None,
        disable_notification: bool,
        channel_id: int | None = None,
    ) -> PublishResult:
        started = time.perf_counter()
        channel_id = channel_id if channel_id is not None else self._channel_id
        if channel_id is None:
            return self._failure(
                channel_id=None,
                started=started,
                error="TELEGRAM_CHANNEL_ID not configured",
            )

        last_error = "unknown error"
        for attempt in range(_MAX_RETRIES + 1):
            try:
                message_id = await self._send_media_once(
                    media_type=media_type,
                    media_url=media_url,
                    caption=caption,
                    thumbnail_url=thumbnail_url,
                    disable_notification=disable_notification,
                    channel_id=channel_id,
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                return PublishResult(
                    success=True,
                    duration_ms=duration_ms,
                    channel_id=channel_id,
                    message_id=message_id,
                    used_media=True,
                )
            except TelegramRetryAfter as exc:
                wait_sec = float(exc.retry_after)
                last_error = f"FloodWait: retry after {wait_sec}s"
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(wait_sec)
            except TelegramAPIError as exc:
                last_error = self._classify_error(exc)
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_RETRY_DELAY_SEC)
            except Exception as exc:
                last_error = repr(exc)
                logger.exception("event=media_publish_failed attempt=%d", attempt + 1)
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_RETRY_DELAY_SEC)

        return self._failure(
            channel_id=channel_id,
            started=started,
            error=last_error,
            used_media=True,
        )

    async def send_to_channel(
        self,
        text: str,
        *,
        disable_notification: bool = False,
        channel_id: int | None = None,
    ) -> PublishResult:
        """Send *text* to the channel with retries. Never raises to callers."""
        started = time.perf_counter()
        channel_id = channel_id if channel_id is not None else self._channel_id

        if channel_id is None:
            logger.error(
                "event=publish_skipped channel_id=None reason='TELEGRAM_CHANNEL_ID not configured'"
            )
            return self._failure(
                channel_id=None,
                started=started,
                error="TELEGRAM_CHANNEL_ID not configured",
            )

        _log_publish(
            "publish_attempt",
            channel_id=channel_id,
            text_len=len(text),
            disable_notification=disable_notification,
        )

        from bot.production_safety.context_holder import get_production_safety

        ps = get_production_safety()
        if ps is not None:
            allowed = await ps.telegram.await_send_slot(channel_id)
            if not allowed:
                return self._failure(
                    channel_id=channel_id,
                    started=started,
                    error="telegram_publish_paused",
                )

        last_error = "unknown error"
        for attempt in range(_MAX_RETRIES + 1):
            try:
                message_id = await self._send_text_once(
                    text,
                    disable_notification=disable_notification,
                    channel_id=channel_id,
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                _log_publish(
                    "publish_success",
                    channel_id=channel_id,
                    duration_ms=duration_ms,
                    message_id=message_id,
                    attempt=attempt + 1,
                )
                if ps is not None:
                    ps.telegram.record_delivery(
                        success=True,
                        latency_ms=float(duration_ms),
                        channel_id=channel_id,
                    )
                    ps.breakers.telegram.record_success()
                return PublishResult(
                    success=True,
                    duration_ms=duration_ms,
                    channel_id=channel_id,
                    message_id=message_id,
                )
            except TelegramRetryAfter as exc:
                wait_sec = float(exc.retry_after)
                if ps is not None:
                    wait_sec = ps.telegram.record_floodwait(wait_sec)
                logger.warning(
                    "event=publish_flood_wait channel_id=%r wait_sec=%r attempt=%r",
                    channel_id,
                    wait_sec,
                    attempt + 1,
                )
                last_error = f"FloodWait: retry after {wait_sec}s"
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(wait_sec)
            except TelegramAPIError as exc:
                last_error = self._classify_error(exc)
                if ps is not None:
                    ps.telegram.record_delivery(success=False, latency_ms=0, channel_id=channel_id)
                logger.warning(
                    "event=publish_retry channel_id=%r attempt=%r error=%r",
                    channel_id,
                    attempt + 1,
                    last_error,
                )
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_RETRY_DELAY_SEC)
            except Exception as exc:
                last_error = repr(exc)
                logger.exception(
                    "event=publish_unexpected channel_id=%r attempt=%r",
                    channel_id,
                    attempt + 1,
                )
                if attempt >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_RETRY_DELAY_SEC)

        return self._failure(
            channel_id=channel_id,
            started=started,
            error=last_error,
        )

    async def verify_startup(self) -> PublishResult:
        """Send a silent probe message and delete it to confirm channel access."""
        if not self.channel_configured:
            logger.warning("event=startup_verify_skipped reason='no channel configured'")
            return PublishResult(
                success=False,
                duration_ms=0,
                channel_id=None,
                error="channel not configured",
            )

        result = await self.send_to_channel(
            "[system] publisher online",
            disable_notification=True,
        )
        if not result.success or result.message_id is None:
            logger.error(
                "event=startup_verify_failed channel_id=%r error=%r",
                self._channel_id,
                result.error,
            )
            return result

        try:
            await self._bot.delete_message(
                chat_id=self._channel_id,
                message_id=result.message_id,
            )
            logger.info(
                "event=startup_verify_ok channel_id=%r duration_ms=%r",
                self._channel_id,
                result.duration_ms,
            )
        except TelegramAPIError as exc:
            logger.warning(
                "event=startup_verify_delete_failed channel_id=%r message_id=%r error=%r",
                self._channel_id,
                result.message_id,
                self._classify_error(exc),
            )
            return PublishResult(
                success=True,
                duration_ms=result.duration_ms,
                channel_id=result.channel_id,
                message_id=result.message_id,
                error="probe sent; delete failed",
            )

        return result
