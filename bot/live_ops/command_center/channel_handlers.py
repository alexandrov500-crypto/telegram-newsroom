from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router
from bot.live_ops.channel_settings import LiveMode
from bot.live_ops.ops_alerts import notify_ops_channel
from bot.operator_console.formatting import split_message

if TYPE_CHECKING:
    from bot.live_ops.controlled_coordinator import ControlledLiveCoordinator

logger = logging.getLogger(__name__)


def register_controlled_live_handlers(*, controlled: ControlledLiveCoordinator | None) -> None:
    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    def _sig() -> dict:
        if controlled is None or controlled._signals_fn is None:
            return {}
        try:
            return controlled._signals_fn()
        except Exception:
            return {}

    def _safe_repo_state() -> dict:
        if controlled is None:
            return {}
        try:
            return controlled.repository.get_state() or {}
        except Exception:
            logger.exception("event=controlled_live_repo_read_failed")
            return {}

    @router.message(Command("live_status"))
    @admin_only("/live_status")
    async def cmd_live_status(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            await _reply(message, controlled.live_status_html())
        except Exception:
            state = _safe_repo_state()
            await _reply(
                message,
                f"<b>Live status (degraded)</b>\nmode={state.get('live_mode')} "
                f"paused={state.get('paused')} frozen={state.get('frozen')}",
            )

    @router.message(Command("canary_status"))
    @admin_only("/canary_status")
    async def cmd_canary_status(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            await _reply(message, controlled.canary.status_html(_safe_repo_state()))
        except Exception:
            await message.answer("Canary status unavailable (partial failure).")

    @router.message(Command("pause_live"))
    @admin_only("/pause_live")
    async def cmd_pause_live(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            controlled.override.pause_live()
            await notify_ops_channel("<b>Live publishing paused</b> (operator)", force=True)
            await _reply(message, "<b>Live publishing paused</b>")
        except Exception:
            controlled.repository.update_state(paused=1)
            await _reply(message, "<b>Paused</b> (degraded path)")

    @router.message(Command("resume_live"))
    @admin_only("/resume_live")
    async def cmd_resume_live(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            controlled.override.resume_live()
            await notify_ops_channel("<b>Live publishing resumed</b>", force=True)
            await _reply(message, "<b>Live publishing resumed</b>")
        except Exception:
            controlled.repository.update_state(paused=0, frozen=0)
            await _reply(message, "<b>Resumed</b> (degraded path)")

    @router.message(Command("freeze_publishing"))
    @admin_only("/freeze_publishing")
    async def cmd_freeze(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            controlled.freeze.freeze_publishing(reason="operator_command")
            controlled.override.freeze_publishing()
        except Exception:
            controlled.repository.update_state(frozen=1, paused=1)
        await notify_ops_channel("<b>Publishing frozen</b> — operator command", force=True)
        await _reply(message, "<b>Publishing frozen</b>")

    @router.message(Command("rollback_last_batch"))
    @admin_only("/rollback_last_batch")
    async def cmd_rollback(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            result = controlled.rollback.rollback_last_batch()
        except Exception:
            from bot.runtime.state import runtime_state

            runtime_state.shadow_publish_only = True
            controlled.repository.update_state(paused=1, live_mode=LiveMode.SHADOW.value)
            result = {"shadow": True, "paused": True, "degraded": True}
        await notify_ops_channel(
            f"<b>Rollback batch</b> shadow={result.get('shadow')} paused={result.get('paused')}",
            force=True,
        )
        await _reply(
            message,
            f"<b>Rollback initiated</b>\nShadow: {result.get('shadow')} · "
            f"paused: {result.get('paused')}",
        )

    @router.message(Command("review_recent_posts"))
    @admin_only("/review_recent_posts")
    async def cmd_review(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            rows = controlled.repository.recent_publishes(limit=8)
            traces = controlled.publish_trace.recent(limit=5)
        except Exception:
            await message.answer("Review unavailable.")
            return
        lines = ["<b>Recent publish attempts</b>"]
        for r in rows:
            status = "✓" if r.get("passed") else "✗"
            lines.append(
                f"{status} #{r['pending_news_id']} [{r['live_mode']}] {r['created_at'][:16]}",
            )
        if traces:
            lines.append("\n<b>Traces</b>")
            for t in traces[:5]:
                lines.append(
                    f"#{t.get('post_id')} {t.get('guard_result')} pub={t.get('published')}",
                )
        if len(lines) == 1:
            lines.append("No publish log yet.")
        await _reply(message, "\n".join(lines))

    @router.message(Command("operator_feedback"))
    @admin_only("/operator_feedback")
    async def cmd_feedback(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            await _reply(message, controlled.feedback.feedback_html())
        except Exception:
            await message.answer("Feedback metrics unavailable.")

    @router.message(Command("mark_bad_post"))
    @admin_only("/mark_bad_post")
    async def cmd_mark_bad(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Usage: /mark_bad_post &lt;pending_news_id&gt; [source]")
            return
        pid = int(parts[1])
        source = parts[2] if len(parts) > 2 else ""
        try:
            controlled.override.mark_post(
                pending_news_id=pid,
                good=False,
                operator_id=message.from_user.id if message.from_user else None,
            )
            q = controlled.on_mark_bad(source=source, pending_news_id=pid) if source else None
            controlled.feedback.update_derived_scores()
            extra = ""
            if q and q.get("quarantined"):
                extra = f"\nSource <code>{q['source']}</code> quarantined until {q.get('cooldown_until', '')[:16]}"
                await notify_ops_channel(
                    f"<b>Source quarantine</b> {q['source']}",
                    force=True,
                )
            await _reply(message, f"Marked #{pid} as bad{extra}")
        except Exception:
            controlled.repository.rate_post(
                pending_news_id=pid,
                rating="bad",
                operator_id=message.from_user.id if message.from_user else None,
            )
            await _reply(message, f"Marked #{pid} bad (degraded path)")

    @router.message(Command("mark_good_post"))
    @admin_only("/mark_good_post")
    async def cmd_mark_good(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Usage: /mark_good_post &lt;pending_news_id&gt;")
            return
        pid = int(parts[1])
        try:
            controlled.override.mark_post(
                pending_news_id=pid,
                good=True,
                operator_id=message.from_user.id if message.from_user else None,
            )
            controlled.feedback.update_derived_scores()
            await _reply(message, f"Marked #{pid} as good")
        except Exception:
            await _reply(message, f"Mark good failed for #{pid}")

    @router.message(Command("live_incidents"))
    @admin_only("/live_incidents")
    async def cmd_incidents(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            rows = controlled.repository.recent_incidents(limit=10)
        except Exception:
            await message.answer("Incidents unavailable.")
            return
        lines = ["<b>Live incidents</b>"]
        for r in rows:
            lines.append(f"• [{r['severity']}] {r['incident_type']} {r['created_at'][:16]}")
        if len(lines) == 1:
            lines.append("No incidents recorded.")
        await _reply(message, "\n".join(lines))

    @router.message(Command("channel_health"))
    @admin_only("/channel_health")
    async def cmd_channel_health(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            await _reply(message, controlled.channel_health_html(_sig()))
        except Exception:
            await _reply(message, controlled.live_status_html())

    @router.message(Command("live_dashboard"))
    @admin_only("/live_dashboard")
    async def cmd_dashboard(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        try:
            await _reply(message, controlled.dashboard_html(_sig()))
        except Exception:
            await _reply(message, "<b>Dashboard degraded</b> — use /live_status")

    @router.message(Command("preview_post"))
    @admin_only("/preview_post")
    async def cmd_preview_post(message: Message) -> None:
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Usage: /preview_post &lt;pending_news_id&gt;")
            return
        try:
            news_id = int(parts[1])
        except ValueError:
            await message.answer("Invalid pending_news_id.")
            return
        from bot.editorial.preview import build_post_preview, format_preview_operator_html
        from bot.storage.db import default_db_path, init_database
        from bot.storage.editorial_repository import EditorialRepository

        try:
            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            editorial = EditorialRepository(db_path)
            item = editorial.get_by_id(news_id)
            if item is None:
                await message.answer(f"No pending news #{news_id}.")
                return
            preview = await build_post_preview(item)
            await _reply(message, format_preview_operator_html(preview))
        except Exception:
            logger.exception("event=preview_post_failed pending_news_id=%s", news_id)
            await message.answer(f"Preview failed for #{news_id}.")

    @router.message(Command("ops_consolidation"))
    @admin_only("/ops_consolidation")
    async def cmd_ops_consolidation(message: Message) -> None:
        try:
            from bot.ops_consolidation.service import consolidation_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, consolidation_html(db_path=db_path))
        except Exception:
            logger.exception("event=ops_consolidation_failed")
            await message.answer("Consolidation report unavailable.")

    @router.message(Command("resilience_status"))
    @admin_only("/resilience_status")
    async def cmd_resilience_status(message: Message) -> None:
        try:
            from bot.ops_resilience.service import resilience_status_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, resilience_status_html(db_path=db_path))
        except Exception:
            logger.exception("event=resilience_status_failed")
            await message.answer("Resilience status unavailable.")

    @router.message(Command("weekly_review"))
    @admin_only("/weekly_review")
    async def cmd_weekly_review(message: Message) -> None:
        try:
            from bot.ops_evidence.service import weekly_review_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, weekly_review_html(db_path=db_path))
        except Exception:
            logger.exception("event=weekly_review_failed")
            await message.answer("Weekly operational review unavailable.")

    @router.message(Command("trust_calibration"))
    @admin_only("/trust_calibration")
    async def cmd_trust_calibration(message: Message) -> None:
        try:
            from bot.trust_calibration.service import trust_calibration_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, trust_calibration_html(db_path=db_path))
        except Exception:
            logger.exception("event=trust_calibration_failed")
            await message.answer("Trust calibration report unavailable.")

    @router.message(Command("ops_storage"))
    @admin_only("/ops_storage")
    async def cmd_ops_storage(message: Message) -> None:
        try:
            from bot.ops_lifecycle.storage_report import build_ops_storage_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, build_ops_storage_html(db_path))
        except Exception:
            logger.exception("event=ops_storage_failed")
            await message.answer("Ops storage report unavailable.")

    @router.message(Command("operator_digest"))
    @admin_only("/operator_digest")
    async def cmd_operator_digest(message: Message) -> None:
        try:
            from bot.operator_ux.service import operator_digest_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, operator_digest_html(db_path=db_path))
        except Exception:
            logger.exception("event=operator_digest_failed")
            await message.answer("Operator digest unavailable.")

    @router.message(Command("attention_queue"))
    @admin_only("/attention_queue")
    async def cmd_attention_queue(message: Message) -> None:
        try:
            from bot.operator_ux.service import attention_queue_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, attention_queue_html(db_path=db_path))
        except Exception:
            logger.exception("event=attention_queue_failed")
            await message.answer("Attention queue unavailable.")

    @router.message(Command("priority_queue"))
    @admin_only("/priority_queue")
    async def cmd_priority_queue(message: Message) -> None:
        try:
            from bot.editorial.priority.service import priority_queue_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, priority_queue_html(limit=12, db_path=db_path))
        except Exception:
            logger.exception("event=priority_queue_failed")
            await message.answer("Priority queue unavailable.")

    @router.message(Command("storyline"))
    @admin_only("/storyline")
    async def cmd_storyline(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /storyline &lt;storyline_id&gt;")
            return
        storyline_id = parts[1].strip()
        try:
            from bot.editorial.memory.service import storyline_html
            from bot.storage.db import default_db_path, init_database

            db_path = (
                controlled.repository._db_path
                if controlled is not None
                else default_db_path()
            )
            init_database(db_path)
            await _reply(message, storyline_html(storyline_id, db_path=db_path))
        except Exception:
            logger.exception("event=storyline_view_failed id=%s", storyline_id)
            await message.answer(f"Storyline unavailable for {storyline_id}.")

    @router.message(Command("publish_trace"))
    @admin_only("/publish_trace")
    async def cmd_publish_trace(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Usage: /publish_trace &lt;pending_news_id&gt;")
            return
        await _reply(message, controlled.trace_html(int(parts[1])))

    @router.message(Command("source_quarantine"))
    @admin_only("/source_quarantine")
    async def cmd_quarantine(message: Message) -> None:
        if controlled is None:
            await message.answer("Controlled live layer offline.")
            return
        await _reply(message, controlled.source_quarantine.status_html())

    @router.message(Command("runtime_identity"))
    @admin_only("/runtime_identity")
    async def cmd_runtime_identity(message: Message) -> None:
        import json

        from bot.runtime.instance import runtime_identity_snapshot
        from bot.runtime.loop_manifest import runtime_loops_classification
        from bot.runtime.profile import get_runtime_capabilities

        snap = runtime_identity_snapshot()
        caps = get_runtime_capabilities()
        classified = runtime_loops_classification(caps)
        lines = [
            "<b>Runtime identity</b>",
            f"<pre>{json.dumps(snap, indent=2)}</pre>",
            f"Profile: <code>{caps.profile.value}</code>",
            f"Monitored loops: <code>{', '.join(classified['active'] + classified['passive']) or 'none'}</code>",
        ]
        await _reply(message, "\n".join(lines))

    @router.message(Command("pilot_preflight"))
    @admin_only("/pilot_preflight")
    async def cmd_pilot_preflight(message: Message) -> None:
        from bot.live_ops.pilot_readiness import (
            evaluate_pilot_db,
            evaluate_pilot_env,
            persistence_snapshot,
        )
        from bot.storage.db import default_db_path, init_database

        env = evaluate_pilot_env()
        lines = ["<b>Pilot preflight</b>", f"Ready: {'yes' if env.ready else 'no'}"]
        for c in env.checks:
            mark = "✓" if c.passed else "✗"
            lines.append(f"{mark} {c.name}: {c.detail[:60]}")
        try:
            if controlled is not None:
                db_path = controlled.repository._db_path
            else:
                db_path = default_db_path()
            init_database(db_path)
            db = evaluate_pilot_db(db_path)
            lines.append(f"\nDB tables: {'ok' if db.ready else 'missing'}")
            snap = persistence_snapshot(db_path)
            lines.append(
                f"Trace: {snap.get('trace_count', 0)} · "
                f"metrics: {snap.get('metrics_count', 0)} · "
                f"incidents: {snap.get('incidents_count', 0)}",
            )
            if controlled is not None and controlled._startup_report:
                lines.append(
                    f"Startup: passed={controlled._startup_report.passed} "
                    f"shadow={controlled._startup_report.forced_shadow}",
                )
        except Exception:
            lines.append("DB check failed (degraded)")
        await _reply(message, "\n".join(lines))
