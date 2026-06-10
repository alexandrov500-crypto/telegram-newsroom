"""Scheduler: weekly Growth Validation report to admin."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram.enums import ParseMode

from app.growth_layer.validation.service import load_growth_validation_bundle
from app.growth_layer.validation.weekly_report import build_weekly_growth_report_from_db
from db.growth_validation_repository import list_post_growth_validation
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("GROWTH_WEEKLY_REPORT_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _in_weekly_window(now_local: datetime) -> bool:
    """Monday 09:00–10:59 local by default."""
    try:
        weekday = int(os.getenv("GROWTH_WEEKLY_REPORT_WEEKDAY", "0"))
    except ValueError:
        weekday = 0
    try:
        hour_start = int(os.getenv("GROWTH_WEEKLY_REPORT_HOUR_START", "9"))
        hour_end = int(os.getenv("GROWTH_WEEKLY_REPORT_HOUR_END", "11"))
    except ValueError:
        hour_start, hour_end = 9, 11
    return now_local.weekday() == weekday and hour_start <= now_local.hour < hour_end


async def run_growth_validation_weekly_report(ctx: object) -> dict[str, object]:
    settings = ctx.settings  # type: ignore[attr-defined]
    bot = ctx.bot  # type: ignore[attr-defined]
    result: dict[str, object] = {"sent": False}

    if not _enabled():
        result["reason"] = "disabled"
        return result

    tz_name = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now(UTC)

    if not _in_weekly_window(now_local):
        result["reason"] = "outside_window"
        return result

    state_path = Path(settings.runtime_state_dir) / "growth_weekly_report_state.json"
    week_key = now_local.strftime("%Y-W%W")
    if state_path.is_file():
        try:
            prev = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and prev.get("week_key") == week_key:
                result["reason"] = "already_sent"
                return result
        except (json.JSONDecodeError, OSError):
            pass

    if getattr(settings, "dry_run", False):
        result["reason"] = "dry_run"
        return result

    async with session_scope() as session:
        html = await build_weekly_growth_report_from_db(session, channel_id=int(settings.channel_id))
        bundle = await load_growth_validation_bundle(session, limit=100)
        segment_rows = await list_post_growth_validation(session, limit=500, final_only=True)
        enriched_rows: list[dict] = []
        try:
            from app.growth_layer.editorial.enriched_rows import load_enriched_validation_rows

            enriched_rows = await load_enriched_validation_rows(session, limit=500)
        except Exception:
            enriched_rows = []

    try:
        await bot.send_message(
            chat_id=int(settings.admin_user_id),
            text=html,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        result["sent"] = True
    except Exception as exc:
        log_event(logger, "growth.validation.weekly_report_failed", error=repr(exc)[:200])
        result["reason"] = f"send_failed:{repr(exc)[:80]}"
        return result

    decision_path = Path(settings.runtime_state_dir) / "growth_format_decision.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(json.dumps(bundle.decision.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from app.growth_layer.segments.routing import persist_segment_decisions_snapshot

        persist_segment_decisions_snapshot(settings.runtime_state_dir, segment_rows)
    except Exception as exc:
        log_event(logger, "growth.segment_snapshot_failed", error=repr(exc)[:120])
    try:
        from app.growth_layer.editorial.snapshot import persist_editorial_intelligence_snapshot

        if enriched_rows:
            persist_editorial_intelligence_snapshot(settings.runtime_state_dir, enriched_rows)
    except Exception as exc:
        log_event(logger, "growth.editorial_snapshot_failed", error=repr(exc)[:120])
    try:
        from app.growth_layer.advisor_validation.reporting import (
            build_advisor_effectiveness_snapshot,
            persist_advisor_effectiveness_snapshot,
        )
        from db.advisor_outcomes_repository import list_advisor_outcomes
        from db.growth_advice_repository import list_draft_growth_advice

        async with session_scope() as session:
            outcomes = await list_advisor_outcomes(session, limit=2000)
            advice = await list_draft_growth_advice(session, limit=500)
            val_rows = await list_post_growth_validation(session, limit=500, final_only=True)
        advice_ids = {int(r["draft_id"]) for r in advice if r.get("draft_id") is not None}
        adv_snap = build_advisor_effectiveness_snapshot(outcomes, validation_rows=val_rows, advice_draft_ids=advice_ids)
        persist_advisor_effectiveness_snapshot(settings.runtime_state_dir, adv_snap)
        from app.growth_layer.policy.policy_registry import build_policy_registry, persist_policy_registry

        policy_reg = build_policy_registry(outcomes, advice_rows=advice, effectiveness_snapshot=adv_snap)
        persist_policy_registry(settings.runtime_state_dir, policy_reg)
        from app.growth_layer.strategy.strategy_reporting import (
            build_editorial_strategy_snapshot,
            persist_editorial_strategy_snapshot,
        )

        strat = build_editorial_strategy_snapshot(val_rows)
        persist_editorial_strategy_snapshot(settings.runtime_state_dir, strat)
        from app.growth_layer.simulation.simulation_report import (
            build_editorial_simulation_snapshot,
            persist_editorial_simulation_snapshot,
        )

        sim = build_editorial_simulation_snapshot(strat)
        persist_editorial_simulation_snapshot(settings.runtime_state_dir, sim)
    except Exception as exc:
        log_event(logger, "growth.advisor_snapshot_failed", error=repr(exc)[:120])
    state_path.write_text(
        json.dumps({"week_key": week_key, "sent_at": datetime.now(UTC).isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )
    log_event(logger, "growth.validation.weekly_report_sent", week_key=week_key)
    return result


async def run_growth_validation_tick(ctx: object) -> dict[str, object]:
    """Lightweight tick: persist format + segment decision snapshots (no Telegram)."""
    settings = ctx.settings  # type: ignore[attr-defined]
    result: dict[str, object] = {"updated": False}
    if os.getenv("GROWTH_VALIDATION_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        result["reason"] = "disabled"
        return result
    async with session_scope() as session:
        bundle = await load_growth_validation_bundle(session, limit=100)
        segment_rows = await list_post_growth_validation(session, limit=500, final_only=True)
        enriched_rows = []
        try:
            from app.growth_layer.editorial.enriched_rows import load_enriched_validation_rows

            enriched_rows = await load_enriched_validation_rows(session, limit=500)
        except Exception:
            enriched_rows = []
    path = Path(settings.runtime_state_dir) / "growth_format_decision.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.decision.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from app.growth_layer.segments.routing import persist_segment_decisions_snapshot

        seg_snapshot = persist_segment_decisions_snapshot(settings.runtime_state_dir, segment_rows)
        result["segment_segments"] = len((seg_snapshot.get("segments") or {}))
    except Exception as exc:
        log_event(logger, "growth.segment_snapshot_failed", error=repr(exc)[:120])
    try:
        from app.growth_layer.editorial.snapshot import persist_editorial_intelligence_snapshot

        if enriched_rows:
            persist_editorial_intelligence_snapshot(settings.runtime_state_dir, enriched_rows)
            result["editorial_intelligence"] = len(enriched_rows)
    except Exception as exc:
        log_event(logger, "growth.editorial_snapshot_failed", error=repr(exc)[:120])
    try:
        from app.growth_layer.advisor_validation.reporting import persist_advisor_effectiveness_snapshot
        from db.advisor_outcomes_repository import list_advisor_outcomes
        from db.growth_advice_repository import list_draft_growth_advice

        async with session_scope() as session:
            outcomes = await list_advisor_outcomes(session, limit=2000)
            advice = await list_draft_growth_advice(session, limit=500)
            val_rows = await list_post_growth_validation(session, limit=500, final_only=True)
        advice_ids = {int(r["draft_id"]) for r in advice if r.get("draft_id") is not None}
        from app.growth_layer.advisor_validation.reporting import build_advisor_effectiveness_snapshot

        snap = build_advisor_effectiveness_snapshot(outcomes, validation_rows=val_rows, advice_draft_ids=advice_ids)
        persist_advisor_effectiveness_snapshot(settings.runtime_state_dir, snap)
        result["advisor_effectiveness"] = snap.get("advisor_reliability")
        from app.growth_layer.policy.policy_registry import build_policy_registry, persist_policy_registry

        policy_reg = build_policy_registry(outcomes, advice_rows=advice, effectiveness_snapshot=snap)
        persist_policy_registry(settings.runtime_state_dir, policy_reg)
        result["policy_trusted"] = policy_reg.get("trusted_recommendations")
        from app.growth_layer.strategy.strategy_reporting import (
            build_editorial_strategy_snapshot,
            persist_editorial_strategy_snapshot,
        )

        strat = build_editorial_strategy_snapshot(val_rows)
        persist_editorial_strategy_snapshot(settings.runtime_state_dir, strat)
        result["strategy_score"] = (strat.get("scorecard") or {}).get("strategy_score")
        from app.growth_layer.simulation.simulation_report import (
            build_editorial_simulation_snapshot,
            persist_editorial_simulation_snapshot,
        )

        sim = build_editorial_simulation_snapshot(strat)
        persist_editorial_simulation_snapshot(settings.runtime_state_dir, sim)
        result["simulation_best"] = sim.get("best_scenario")
    except Exception as exc:
        log_event(logger, "growth.advisor_snapshot_failed", error=repr(exc)[:120])
    result["updated"] = True
    result["decision"] = bundle.decision.recommended_mode
    return result
