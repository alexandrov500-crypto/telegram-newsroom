from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.operator_console.aggregation import NotificationAggregator
from bot.operator_console.approval_queue import ApprovalQueueItem, SmartApprovalQueue
from bot.operator_console.digest import (
    format_cognition_digest,
    format_epistemic_digest,
    format_ops_digest,
)
from bot.operator_console.fatigue import FatigueGuard
from bot.operator_console.formatting import alert_footer, clamp_lines, escape, format_header, now_utc_short
from bot.operator_console.incidents import IncidentCorrelator
from bot.operator_console.severity import (
    AlertLevel,
    critical_operator_mention,
    format_level_header,
    score_cognitive,
    score_contradiction_burst,
    score_incident,
    score_ingest,
)
from bot.operator_console.usability import UsabilityTelemetry

if TYPE_CHECKING:
    from bot.operator_console.console import OperatorTelegramConsole
    from bot.settings import BotSettings

logger = logging.getLogger(__name__)

_ROUTE_LABELS = {
    "premium": "geopolitical-analysis",
    "breaking_fast": "breaking-desk",
    "balanced": "general-editorial",
    "cost_guard": "cost-efficient",
}


class OperatorSignalHub:
    """Severity-aware, aggregated, fatigue-protected signal routing."""

    def __init__(self, console: OperatorTelegramConsole, settings: BotSettings) -> None:
        self._console = console
        self._settings = settings
        self._aggregator = NotificationAggregator(
            default_window_sec=float(settings.telegram_ops_agg_window_sec),
        )
        self._fatigue = FatigueGuard(
            max_messages_per_hour=settings.telegram_ops_max_messages_per_hour,
            fatigue_threshold=settings.telegram_ops_fatigue_threshold,
            quiet_hour_start=settings.telegram_ops_quiet_hour_start,
            quiet_hour_end=settings.telegram_ops_quiet_hour_end,
        )
        self._incidents = IncidentCorrelator()
        self._approval_queue = SmartApprovalQueue()
        self._usability = UsabilityTelemetry()
        self._last_contradiction_count = 0
        self._ops_repo: Any | None = None

    def attach_repository(self, repo: Any | None) -> None:
        self._ops_repo = repo

    async def dispatch(
        self,
        text: str,
        *,
        level: AlertLevel,
        category: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        force: bool = False,
        replay_ref: str | None = None,
        thread_id: str | None = None,
        route: str | None = None,
        contradictions: int | None = None,
    ) -> bool:
        if self._fatigue.should_suppress(level) and not force:
            self._fatigue.record_suppressed()
            try:
                from bot.observability.metrics import record_operator_suppressed

                record_operator_suppressed(level.value)
            except Exception:
                pass
            self._usability.record_signal(
                signal_kind=category, severity=level.value, suppressed=True,
            )
            return False

        if level == AlertLevel.CRITICAL:
            text = "🚨 <b>OPERATOR ATTENTION</b>\n" + text
            text += critical_operator_mention(self._settings.admin_user_id_set)
        footer = alert_footer(
            replay_ref=replay_ref,
            route=route,
            contradictions=contradictions,
            bundle=f"incident_{thread_id}" if thread_id and level.rank >= AlertLevel.WARNING.rank else None,
        )
        if footer and footer not in text:
            text += f"\n{footer}"
        if thread_id and thread_id not in text:
            text += f"\nThread <code>{escape(thread_id)}</code>"

        cooldown = {
            AlertLevel.INFO: 120.0,
            AlertLevel.NOTICE: 60.0,
            AlertLevel.WARNING: 15.0,
            AlertLevel.CRITICAL: 0.0,
        }[level]

        sent = await self._console.send_raw(
            clamp_lines(text, max_lines=12),
            category=category,
            cooldown_sec=cooldown,
            reply_markup=reply_markup,
            force=force or level == AlertLevel.CRITICAL,
            silent=level == AlertLevel.INFO,
        )
        if sent:
            self._fatigue.record_send(
                is_alert=level.rank >= AlertLevel.WARNING.rank,
                category=category,
            )
            self._usability.record_signal(signal_kind=category, severity=level.value)
        return sent

    async def notify_ingest(
        self,
        *,
        source: str,
        language: str,
        headline: str,
        outcome: str,
        confidence: float,
        cluster_id: int | None,
        news_id: int | None,
        priority: float,
        duplicate: bool = False,
    ) -> None:
        if not self._settings.telegram_live_ingest_enabled:
            return
        if priority < self._settings.telegram_live_ingest_min_priority and not duplicate:
            return

        level = score_ingest(priority=priority, duplicate=duplicate)
        replay = f"evt_{news_id}" if news_id else None

        if duplicate or level == AlertLevel.INFO:
            self._aggregator.record(
                "ingest",
                {"source": source, "language": language, "headline": headline, "outcome": outcome},
                severity=level,
            )
            self._usability.record_signal(
                signal_kind="ingest", severity=level.value, aggregated=True,
            )
            return

        text = clamp_lines(
            "\n".join(
                [
                    format_level_header("INGEST", level),
                    f"{escape(source or 'unknown')} · {escape(language.upper())} · "
                    f"conf {confidence:.2f} pri {priority:.2f}",
                    escape(headline[:180]),
                    now_utc_short(),
                ]
            ),
            max_lines=8,
        )
        await self.dispatch(
            text, level=level, category="ingest", replay_ref=replay, route="ingest",
        )

    async def notify_cognitive_route(
        self,
        *,
        news_id: int,
        route_decision: Any,
        priority: float,
        contradiction_count: int = 0,
        trust_signal: float = 0.5,
        epistemic_warnings: list[str] | None = None,
    ) -> None:
        if not self._settings.telegram_live_cognitive_enabled:
            return
        if priority < 0.72:
            return
        level = score_cognitive(
            priority=priority,
            contradiction_count=contradiction_count,
            trust=trust_signal,
        )
        label = _ROUTE_LABELS.get(route_decision.strategy, route_decision.strategy)

        if level == AlertLevel.INFO:
            self._aggregator.record(
                "cognitive",
                {"news_id": news_id, "strategy": route_decision.strategy},
                window_sec=180.0,
                severity=level,
            )
            self._usability.record_signal(
                signal_kind="cognitive", severity=level.value, aggregated=True,
            )
            return

        reasons = [route_decision.reason]
        if contradiction_count > 2:
            reasons.append(f"contradictions {contradiction_count}")
        if trust_signal < 0.45:
            reasons.append(f"trust {trust_signal:.2f}")
        text = clamp_lines(
            "\n".join(
                [
                    format_level_header("COGNITIVE ROUTE", level),
                    f"#{news_id} → <b>{escape(label)}</b> · <code>{escape(route_decision.model)}</code>",
                    " · ".join(escape(r) for r in reasons if r)[:300],
                ]
            ),
            max_lines=8,
        )
        await self.dispatch(
            text,
            level=level,
            category="cognitive",
            replay_ref=f"evt_{news_id}",
            route=label,
            contradictions=contradiction_count,
        )

    async def notify_contradiction_burst(
        self,
        *,
        open_count: int,
        top_items: list[dict],
    ) -> None:
        if open_count < self._settings.telegram_live_contradiction_threshold:
            return
        delta = max(0, open_count - self._last_contradiction_count)
        self._last_contradiction_count = open_count
        level = score_contradiction_burst(open_count, delta=delta)

        for item in top_items:
            self._aggregator.record(
                "contradiction",
                {
                    "contradiction_id": item.get("contradiction_id"),
                    "subject_type": item.get("subject_type", "general"),
                    "explanation": item.get("explanation", ""),
                    "severity": item.get("severity", 0),
                },
                severity=level,
            )

        if level.rank < AlertLevel.WARNING.rank and delta < 5:
            self._usability.record_signal(
                signal_kind="contradiction", severity=level.value, aggregated=True,
            )
            return

        flushed = self._aggregator.flush("contradiction")
        if flushed:
            md, agg_id, n, sev = flushed
            thread = self._incidents.correlate(
                "contradiction",
                title=f"Contradiction burst ({n})",
                detail=f"open={open_count} delta={delta}",
                severity=level,
                replay_ref=f"agg_{agg_id}",
            )
            try:
                from bot.observability.metrics import record_operator_aggregated

                record_operator_aggregated("contradiction")
            except Exception:
                pass
            await self.dispatch(
                md,
                level=level,
                category="contradiction_summary",
                replay_ref=f"agg_{agg_id}",
                thread_id=thread.thread_id,
                contradictions=open_count,
            )
            return

        thread = self._incidents.correlate(
            "contradiction",
            title="Contradiction threshold",
            detail=f"open={open_count}",
            severity=level,
        )
        text = (
            f"{format_level_header('CONTRADICTION', level)}\n"
            f"Open <b>{open_count}</b> (+{delta})\n"
            f"/contradictions_queue"
        )
        await self.dispatch(
            text,
            level=level,
            category="contradiction",
            thread_id=thread.thread_id,
            contradictions=open_count,
        )

    async def notify_incident(
        self,
        *,
        kind: str,
        title: str,
        detail: str,
        replay_ref: str | None = None,
        suggested_action: str | None = None,
        mesh_health: float = 1.0,
        open_contradictions: int = 0,
    ) -> None:
        if not self._settings.telegram_live_incident_enabled:
            return
        level = score_incident(
            kind,
            open_contradictions=open_contradictions,
            mesh_health=mesh_health,
        )
        self._fatigue.record_incident_type(kind)
        thread = self._incidents.correlate(
            kind,
            title=title,
            detail=detail,
            severity=level,
            replay_ref=replay_ref,
        )
        agg_kind = {
            "replay": "replay_spike",
            "federation": "federation",
            "misinfo": "misinfo_cluster",
            "topology": "topology",
        }.get(kind.split("_")[0], "")
        if agg_kind and level.rank >= AlertLevel.NOTICE.rank:
            self._aggregator.record(
                agg_kind,
                {"title": title, "detail": detail[:200]},
                severity=level,
            )

        action = suggested_action or thread.suggested_action()
        lines = [
            format_level_header("INCIDENT", level),
            f"<b>{escape(title)}</b>",
            escape(detail[:280]),
            f"Chain: {escape(thread.rca_snippet())}",
            f"→ {escape(action)}",
        ]
        await self.dispatch(
            clamp_lines("\n".join(lines), max_lines=10),
            level=level,
            category=f"incident:{kind[:20]}",
            replay_ref=replay_ref,
            thread_id=thread.thread_id,
            force=level == AlertLevel.CRITICAL,
            contradictions=open_contradictions,
        )
        if self._ops_repo:
            try:
                self._ops_repo.save_incident_thread(self._incidents.to_persist_dict(thread))
            except Exception:
                pass

    def queue_approval(self, **kwargs: Any) -> None:
        if not self._settings.telegram_live_approval_cards:
            return
        self._approval_queue.enqueue(
            ApprovalQueueItem(
                sort_index=-float(kwargs["priority"]),
                news_id=kwargs["news_id"],
                headline=kwargs["headline"],
                summary=kwargs["summary"],
                confidence=kwargs["confidence"],
                epistemic_stability=kwargs["epistemic_stability"],
                contradiction_exposure=kwargs["contradiction_exposure"],
                misinfo_risk=kwargs["misinfo_risk"],
                source_diversity=kwargs["source_diversity"],
                replay_id=f"evt_{kwargs['news_id']}",
                cluster_id=kwargs.get("cluster_id"),
            )
        )

    async def flush_approval_digest(self) -> None:
        if self._fatigue.enter_quiet_burst_collapse() and self._approval_queue.pending_count() > 3:
            items = self._approval_queue.drain_for_digest(8)
            if not items:
                return
            text = self._approval_queue.format_digest_message(items)
            kb = self._approval_queue.batch_keyboard(items, "approve")
            await self.dispatch(
                text,
                level=AlertLevel.WARNING,
                category="approval_batch",
                reply_markup=kb,
            )
            return
        for _ in range(min(self._approval_queue.max_immediate, self._approval_queue.pending_count())):
            batch = self._approval_queue.drain_for_digest(1)
            if not batch:
                break
            item = batch[0]
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅", callback_data=f"op:approve:{item.news_id}"),
                        InlineKeyboardButton(text="❌", callback_data=f"op:reject:{item.news_id}"),
                        InlineKeyboardButton(text="💡", callback_data=f"op:explain:{item.news_id}"),
                    ],
                ]
            )
            await self.dispatch(
                self._approval_queue.format_single_card(item),
                level=AlertLevel.NOTICE if item.confidence >= 0.7 else AlertLevel.WARNING,
                category="approval",
                reply_markup=kb,
                replay_ref=item.replay_id,
            )

    async def flush_aggregates(self) -> int:
        n = 0
        for kind, md, agg_id, count, sev in self._aggregator.flush_all_ready():
            level = sev if count >= 3 else AlertLevel.INFO
            try:
                from bot.observability.metrics import record_operator_aggregated

                record_operator_aggregated(kind)
            except Exception:
                pass
            await self.dispatch(
                md,
                level=level,
                category=f"agg:{kind}",
                replay_ref=f"agg_{agg_id}",
            )
            n += 1
        return n

    async def send_ops_digest(self, signals: dict[str, Any], health: Any) -> None:
        fatigue = self._fatigue.snapshot()
        text = format_ops_digest(health=health, fatigue=fatigue, signals=signals)
        await self.dispatch(text, level=AlertLevel.INFO, category="ops_digest", force=True)

    async def send_cognition_digest(
        self,
        *,
        mesh_health: float,
        reasoning_spend: float = 0.0,
        reasoning_quota: float = 100.0,
    ) -> None:
        text = format_cognition_digest(
            mesh_health=mesh_health,
            reasoning_spend=reasoning_spend,
            reasoning_quota=reasoning_quota,
        )
        await self.dispatch(text, level=AlertLevel.INFO, category="cognition_digest", force=True)

    async def send_epistemic_digest(
        self,
        *,
        open_contradictions: int,
        misinfo_pending: int,
        epistemic_stability: float,
        delta: int = 0,
    ) -> None:
        text = format_epistemic_digest(
            open_contradictions=open_contradictions,
            misinfo_pending=misinfo_pending,
            epistemic_stability=epistemic_stability,
            delta_contradictions=delta,
        )
        level = AlertLevel.WARNING if open_contradictions > 20 else AlertLevel.INFO
        await self.dispatch(text, level=level, category="epistemic_digest", force=True)

    @property
    def fatigue(self) -> FatigueGuard:
        return self._fatigue

    @property
    def usability(self) -> UsabilityTelemetry:
        return self._usability

    @property
    def incidents(self) -> IncidentCorrelator:
        return self._incidents

    @property
    def approval_queue(self) -> SmartApprovalQueue:
        return self._approval_queue
