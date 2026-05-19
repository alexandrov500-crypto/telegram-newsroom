from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aiogram import Bot

from bot.observability.logging_setup import get_logger

logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertManager:
    """Telegram alert sink with cooldown and deduplication."""

    bot: Bot
    chat_id: int | None
    cooldown_sec: int = 300
    _last_sent: dict[str, float] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _dedupe_key(self, severity: AlertSeverity, title: str) -> str:
        raw = f"{severity.value}:{title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    async def send(
        self,
        severity: AlertSeverity,
        title: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> bool:
        if self.chat_id is None:
            logger.warning(
                "event=alert_skipped",
                reason="no_alert_chat_id",
                severity=severity.value,
                title=title,
            )
            return False

        try:
            from bot.week1.context_holder import get_week1

            w1 = get_week1()
            if w1 is not None and not w1.should_surface_alert(
                title=title,
                severity=severity.value,
                symptoms=list((details or {}).keys()) if details else None,
                subsystem=str((details or {}).get("subsystem", "")) or None,
            ):
                logger.info(
                    "event=alert_suppressed_week1",
                    severity=severity.value,
                    title=title,
                )
                return False
        except Exception:
            pass

        key = self._dedupe_key(severity, title)
        now = time.monotonic()
        async with self._lock:
            last = self._last_sent.get(key)
            if last is not None and (now - last) < self.cooldown_sec:
                logger.info(
                    "event=alert_suppressed",
                    severity=severity.value,
                    title=title,
                    cooldown_sec=self.cooldown_sec,
                )
                return False
            self._last_sent[key] = now

        merged: dict[str, Any] = {}
        try:
            from bot.runtime.instance import get_runtime_identity

            ident = get_runtime_identity()
            if ident is not None:
                merged.update(ident.alert_context())
        except Exception:
            pass
        if details:
            merged.update(details)

        body_lines = [f"🚨 [{severity.value.upper()}] {title}"]
        if merged:
            for field_name, value in merged.items():
                body_lines.append(f"{field_name}={value}")
        text = "\n".join(body_lines)[:4000]

        try:
            await self.bot.send_message(self.chat_id, text, disable_notification=False)
            logger.info(
                "event=alert_sent",
                severity=severity.value,
                title=title,
            )
            try:
                from bot.ops_forensics.hooks import record_timeline

                record_timeline(
                    "watchdog_alert",
                    severity=severity.value,
                    details={"title": title, **merged},
                )
            except Exception:
                pass
            return True
        except Exception:
            logger.exception("event=alert_send_failed", title=title)
            return False

    async def info(self, title: str, *, details: dict[str, Any] | None = None) -> bool:
        return await self.send(AlertSeverity.INFO, title, details=details)

    async def warning(self, title: str, *, details: dict[str, Any] | None = None) -> bool:
        return await self.send(AlertSeverity.WARNING, title, details=details)

    async def critical(self, title: str, *, details: dict[str, Any] | None = None) -> bool:
        return await self.send(AlertSeverity.CRITICAL, title, details=details)
