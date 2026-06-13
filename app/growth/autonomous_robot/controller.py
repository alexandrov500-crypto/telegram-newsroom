"""Autonomous growth controller — bounded self-tuning for audience max."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.growth.autonomous_robot.pulse import collect_growth_pulse, format_pulse_telegram
from app.growth.autonomous_robot.tuning_store import (
    TUNING_BOUNDS,
    apply_tuning_overrides_to_env,
    load_tuning_state,
    set_override,
)
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def autonomous_growth_robot_enabled() -> bool:
    return os.getenv("AUTONOMOUS_GROWTH_ROBOT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _cooldown_ok(runtime_dir: str, *, min_minutes: int = 55) -> bool:
    state = load_tuning_state(runtime_dir)
    updated = state.get("updated_at")
    if not updated:
        return True
    try:
        prev = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=UTC)
        return (datetime.now(UTC) - prev).total_seconds() >= min_minutes * 60
    except (TypeError, ValueError):
        return True


def decide_autonomous_adjustments(pulse: dict[str, Any]) -> list[dict[str, Any]]:
    """Return at most one bounded tuning action per tick."""
    actions: list[dict[str, Any]] = []
    target = float(pulse.get("target_posts_per_day") or 28)
    pub_24h = float(pulse.get("published_24h") or 0)
    silence = pulse.get("silence_minutes")
    reject_ratio = float(pulse.get("reject_ratio_24h") or 0)
    momentum = float(pulse.get("engagement_momentum") or 0)
    top_rejects = pulse.get("top_reject_reasons") or []
    top_reason = str(top_rejects[0]["reason"]) if top_rejects else ""

    ueos = _env_float("UEOS_PUBLISH_THRESHOLD", 68)
    gap = _env_float("EDITORIAL_ANTI_PAUSE_GAP_MINUTES", 50)
    interval = _env_float("PUBLISH_CHANNEL_MIN_INTERVAL_SEC", 45)

    # Throughput recovery — silence or under-target volume
    if (silence is not None and float(silence) > 75) or pub_24h < target * 0.55:
        if ueos > TUNING_BOUNDS["UEOS_PUBLISH_THRESHOLD"][0] + 1:
            actions.append(
                {
                    "key": "UEOS_PUBLISH_THRESHOLD",
                    "value": ueos - 2,
                    "reason": f"throughput_recovery silence={silence} pub_24h={pub_24h}",
                }
            )
        elif gap > TUNING_BOUNDS["EDITORIAL_ANTI_PAUSE_GAP_MINUTES"][0] + 4:
            actions.append(
                {
                    "key": "EDITORIAL_ANTI_PAUSE_GAP_MINUTES",
                    "value": gap - 5,
                    "reason": f"anti_pause_tighten silence={silence}",
                }
            )
        elif interval > TUNING_BOUNDS["PUBLISH_CHANNEL_MIN_INTERVAL_SEC"][0] + 4:
            actions.append(
                {
                    "key": "PUBLISH_CHANNEL_MIN_INTERVAL_SEC",
                    "value": interval - 5,
                    "reason": "publish_interval_recovery",
                }
            )

    # Quality guard — too many rejects while publishing enough
    elif reject_ratio > 0.48 and pub_24h >= target * 0.4:
        if "dominance_growth" in top_reason or "growth_reject" in top_reason:
            if ueos < TUNING_BOUNDS["UEOS_PUBLISH_THRESHOLD"][1] - 1:
                actions.append(
                    {
                        "key": "UEOS_PUBLISH_THRESHOLD",
                        "value": ueos + 1,
                        "reason": f"quality_guard reject={reject_ratio} top={top_reason}",
                    }
                )
        elif "not_informative" in top_reason or "truncated" in top_reason:
            if ueos > TUNING_BOUNDS["UEOS_PUBLISH_THRESHOLD"][0] + 1:
                actions.append(
                    {
                        "key": "UEOS_PUBLISH_THRESHOLD",
                        "value": ueos - 1,
                        "reason": f"informative_relax reject={reject_ratio}",
                    }
                )

    # Engagement optimization — enough volume but weak momentum
    elif momentum < 0.32 and pub_24h >= target * 0.75 and reject_ratio < 0.35:
        if ueos < TUNING_BOUNDS["UEOS_PUBLISH_THRESHOLD"][1] - 0.5:
            actions.append(
                {
                    "key": "UEOS_PUBLISH_THRESHOLD",
                    "value": ueos + 1,
                    "reason": f"engagement_selectivity momentum={momentum}",
                }
            )

    return actions[:1]


def _weekly_report_due(settings: Any) -> bool:
    if os.getenv("AUTONOMOUS_WEEKLY_REPORT_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    tz_name = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
    try:
        from zoneinfo import ZoneInfo

        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now(UTC)
    try:
        weekday = int(os.getenv("AUTONOMOUS_WEEKLY_REPORT_WEEKDAY", "0"))
        hour = int(os.getenv("AUTONOMOUS_WEEKLY_REPORT_HOUR", "10"))
    except ValueError:
        weekday, hour = 0, 10
    return now_local.weekday() == weekday and now_local.hour == hour


async def _maybe_send_weekly_growth_report(
    ctx: object,
    settings: Any,
    runtime_dir: str,
    pulse: dict[str, Any],
) -> None:
    if not _weekly_report_due(settings):
        return
    state_path = Path(runtime_dir) / "autonomous_weekly_report_state.json"
    tz_name = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
    try:
        from zoneinfo import ZoneInfo

        week_key = datetime.now(ZoneInfo(tz_name)).strftime("%Y-W%W")
    except Exception:
        week_key = datetime.now(UTC).strftime("%Y-W%W")

    if state_path.is_file():
        try:
            prev = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and prev.get("week_key") == week_key:
                return
        except (OSError, json.JSONDecodeError):
            pass

    from app.growth.autonomous_robot.weekly_report import build_weekly_growth_summary, format_weekly_growth_report

    channel_id = int(getattr(settings, "target_channel_id", 0) or getattr(settings, "channel_id", 0) or 0)
    summary = await build_weekly_growth_summary(
        runtime_dir=runtime_dir,
        channel_id=channel_id or None,
        pulse=pulse,
    )
    text = format_weekly_growth_report(summary)
    bot = getattr(ctx, "bot", None)
    admin_id = int(getattr(settings, "admin_user_id", 0) or 0)
    if bot and admin_id:
        await bot.send_message(admin_id, text[:3900], disable_web_page_preview=True)
    state_path.write_text(json.dumps({"week_key": week_key, "sent_at": datetime.now(UTC).isoformat()}), encoding="utf-8")


async def run_autonomous_growth_tick(ctx: object) -> dict[str, Any]:
    """Hourly: pulse → optional tuning → notify operator on material change."""
    settings = ctx.settings  # type: ignore[attr-defined]
    runtime_dir = str(settings.runtime_state_dir)
    result: dict[str, Any] = {"enabled": autonomous_growth_robot_enabled()}

    if not autonomous_growth_robot_enabled():
        result["reason"] = "disabled"
        return result

    apply_tuning_overrides_to_env(runtime_dir)

    pulse = await collect_growth_pulse(
        runtime_dir=runtime_dir,
        channel_id=int(getattr(settings, "target_channel_id", 0) or 0) or None,
    )
    result["pulse"] = pulse

    pulse_path = Path(runtime_dir) / "growth_pulse_latest.json"
    pulse_path.write_text(json.dumps(pulse, indent=2, ensure_ascii=False), encoding="utf-8")

    phase2: dict[str, Any] = {}
    try:
        from app.growth.autonomous_robot.peak_hours import current_peak_verdict
        from app.growth.autonomous_robot.source_curator import curate_fastlane_sources
        from app.growth.autonomous_robot.topic_boost import refresh_topic_boost_matrix

        phase2["topic_boost"] = refresh_topic_boost_matrix(runtime_dir)
        tz = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
        phase2["peak_hour"] = current_peak_verdict(newsroom_tz=tz).reason
        baseline = [str(h) for h in getattr(settings, "source_channels", ()) or ()]
        phase2["source_curation"] = await curate_fastlane_sources(runtime_dir, env_baseline=baseline)
        pulse["phase2"] = {
            "top_topics": phase2["topic_boost"].get("top_topics") or [],
            "peak_hour": phase2["peak_hour"],
            "fastlane_count": len((phase2["source_curation"].get("fastlane") or [])),
        }
        result["phase2"] = phase2
    except Exception as exc:
        log_event(logger, "growth_robot.phase2_failed", error=repr(exc)[:160])
        result["phase2_error"] = repr(exc)[:160]

    actions: list[dict[str, Any]] = []
    if _cooldown_ok(runtime_dir):
        actions = decide_autonomous_adjustments(pulse)
        for act in actions:
            set_override(runtime_dir, act["key"], float(act["value"]), reason=str(act["reason"]))
        result["adjustments"] = actions
    else:
        result["adjustments"] = []
        result["adjustments_skipped"] = "cooldown"

    # Notify on critical health or adjustment
    try:
        if pulse.get("health") == "critical" or actions:
            bot = getattr(ctx, "bot", None)
            admin_id = int(getattr(settings, "admin_user_id", 0) or 0)
            if bot and admin_id:
                msg = format_pulse_telegram(pulse)
                if actions:
                    msg += "\n\n🤖 " + actions[0]["reason"]
                await bot.send_message(admin_id, msg[:3900], disable_web_page_preview=True)
    except Exception as exc:
        log_event(logger, "growth_robot.notify_failed", error=repr(exc)[:120])

    try:
        await _maybe_send_weekly_growth_report(ctx, settings, runtime_dir, pulse)
    except Exception as exc:
        log_event(logger, "growth_robot.weekly_failed", error=repr(exc)[:120])

    log_event(
        logger,
        "growth_robot.tick_complete",
        health=pulse.get("health"),
        health_score=pulse.get("health_score"),
        published_24h=pulse.get("published_24h"),
        silence_minutes=pulse.get("silence_minutes"),
        adjustments=len(actions),
    )
    return result
