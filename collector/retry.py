from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError

from utils.metrics import inc
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def ensure_connected(client: TelegramClient) -> None:
    if not client.is_connected():
        from collector.telethon_connect import connect_telethon_resilient

        ok = await connect_telethon_resilient(client, label="ensure_connected")
        if not ok:
            raise ConnectionError("Telethon connect timed out or network unreachable")


async def with_telethon_retries(
    label: str,
    op: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            out = await op()
            if attempt > 1:
                log_event(
                    logger,
                    "telethon.op_recovered_after_retry",
                    label=label,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
            return out
        except SessionPasswordNeededError:
            logger.error(
                "Telethon session requires 2FA password (SessionPasswordNeededError). "
                "Recreate TELETHON_SESSION_STRING for an account without interactive 2FA in this MVP. label=%s",
                label,
            )
            raise
        except FloodWaitError as exc:
            inc("telethon_flood_waits")
            wait_s = float(getattr(exc, "seconds", 0) or 0)
            try:
                from app.observability.telegram_production import record_flood_wait

                record_flood_wait(wait_sec=wait_s, source=f"collector:{label}")
            except Exception:
                pass
            wait_s = max(wait_s, base_delay_s * attempt)
            logger.warning(
                "Telethon FloodWait on %s attempt=%s/%s wait_s=%s",
                label,
                attempt,
                max_attempts,
                wait_s,
            )
            await asyncio.sleep(wait_s)
            last_exc = exc
        except (RPCError, OSError, TimeoutError, asyncio.TimeoutError) as exc:
            last_exc = exc
            delay = min(30.0, base_delay_s * (2 ** (attempt - 1)))
            logger.warning(
                "Telethon transient error on %s attempt=%s/%s: %s; retry in %.1fs",
                label,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
        except Exception:
            raise

    assert last_exc is not None
    raise last_exc
