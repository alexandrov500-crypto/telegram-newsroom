from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup

from bot.operator_console.formatting import split_message
from bot.operator_console.hub import OperatorSignalHub
from bot.operator_console.rate_limit import RateLimiter
from bot.settings import BotSettings

logger = logging.getLogger(__name__)


@dataclass
class OperatorTelegramConsole:
    """Live operational feed into Telegram for staging operators."""

    bot: Bot
    settings: BotSettings
    _limiter: RateLimiter | None = None
    _hub: OperatorSignalHub | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._limiter = RateLimiter(default_cooldown_sec=45.0)
        self._hub = OperatorSignalHub(self, self.settings)

    @property
    def hub(self) -> OperatorSignalHub:
        assert self._hub is not None
        return self._hub

    @property
    def enabled(self) -> bool:
        return bool(self.settings.telegram_live_ingest_enabled or self.settings.is_staging)

    @property
    def ingest_chat_id(self) -> int | None:
        return (
            self.settings.telegram_live_ingest_chat_id
            or self.settings.telegram_operator_chat_id
            or self.settings.alert_chat_id
        )

    async def send_raw(
        self,
        text: str,
        *,
        category: str = "general",
        cooldown_sec: float | None = None,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: InlineKeyboardMarkup | None = None,
        force: bool = False,
        silent: bool = False,
    ) -> bool:
        return await self.send(
            text,
            category=category,
            cooldown_sec=cooldown_sec,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            force=force,
            silent=silent,
        )

    async def send(
        self,
        text: str,
        *,
        category: str = "general",
        cooldown_sec: float | None = None,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: InlineKeyboardMarkup | None = None,
        force: bool = False,
        silent: bool = False,
    ) -> bool:
        chat_id = self.ingest_chat_id
        if chat_id is None:
            return False
        if not force and self._limiter and not self._limiter.allow(
            category, cooldown_sec=cooldown_sec
        ):
            logger.debug("event=operator_console_suppressed category=%s", category)
            return False
        try:
            chunks = split_message(text)
            for i, chunk in enumerate(chunks):
                await self.bot.send_message(
                    chat_id,
                    chunk,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup if i == len(chunks) - 1 else None,
                    disable_notification=silent or category in ("ingest", "burnin", "ops_digest"),
                )
            try:
                from bot.observability.metrics import record_operator_telegram_message

                record_operator_telegram_message(category)
            except Exception:
                pass
            return True
        except Exception:
            logger.exception("event=operator_console_send_failed category=%s", category)
            return False

    async def notify_ingest(self, **kwargs: Any) -> None:
        await self.hub.notify_ingest(**kwargs)

    async def notify_cognitive_route(self, **kwargs: Any) -> None:
        await self.hub.notify_cognitive_route(**kwargs)

    async def notify_contradiction_alert(self, **kwargs: Any) -> None:
        await self.hub.notify_contradiction_burst(**kwargs)

    async def notify_burnin_status(self, summary: dict[str, Any]) -> None:
        if not self.settings.telegram_live_burnin_hourly:
            return
        from bot.operator_console.formatting import escape, format_header, now_utc_short

        lag = summary.get("replay_lag", "healthy")
        text = (
            f"{format_header('BURN-IN', 'ok')}\n"
            f"Ingested: <b>{summary.get('ingested_session', 0):,}</b> · "
            f"lag=<b>{escape(str(lag))}</b>\n"
            f"Contradictions: <b>{summary.get('open_contradictions', 0)}</b> · "
            f"misinfo=<b>{summary.get('misinfo_alerts', 0)}</b>\n"
            f"Mesh: <b>{summary.get('mesh_health', 0):.2f}</b> · "
            f"storage +<b>{summary.get('storage_growth_mb', 0):.0f}MB</b>\n"
            f"{now_utc_short()}"
        )
        await self.send_raw(text, category="burnin", cooldown_sec=3500.0, force=True)

    async def notify_incident(
        self,
        *,
        title: str,
        severity: str = "warn",
        detail: str,
        kind: str | None = None,
        replay_ref: str | None = None,
        suggested_action: str | None = None,
        bundle_ref: str | None = None,
        mesh_health: float = 1.0,
        open_contradictions: int = 0,
    ) -> None:
        incident_kind = kind or _infer_incident_kind(title, severity)
        if bundle_ref and not replay_ref:
            replay_ref = bundle_ref
        await self.hub.notify_incident(
            kind=incident_kind,
            title=title,
            detail=detail,
            replay_ref=replay_ref,
            suggested_action=suggested_action,
            mesh_health=mesh_health,
            open_contradictions=open_contradictions,
        )

    async def send_approval_card(
        self,
        *,
        news_id: int,
        headline: str,
        summary: str,
        confidence: float,
        epistemic_stability: float,
        contradiction_exposure: int,
        misinfo_risk: float,
        source_diversity: int,
        replay_id: str = "",
        priority: float | None = None,
        cluster_id: int | None = None,
    ) -> None:
        self.hub.queue_approval(
            news_id=news_id,
            headline=headline,
            summary=summary,
            confidence=confidence,
            epistemic_stability=epistemic_stability,
            contradiction_exposure=contradiction_exposure,
            misinfo_risk=misinfo_risk,
            source_diversity=source_diversity,
            priority=priority if priority is not None else confidence,
            cluster_id=cluster_id,
        )

    async def flush_pending_signals(self) -> None:
        await self.hub.flush_aggregates()
        await self.hub.flush_approval_digest()


def _infer_incident_kind(title: str, severity: str) -> str:
    lower = title.lower()
    for token in ("replay", "federation", "misinfo", "contradiction", "topology", "storage"):
        if token in lower:
            return token
    if severity == "critical":
        return "critical_ops"
    return "general"
