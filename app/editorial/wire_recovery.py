"""Wire recovery — top-channel throughput mode after silence or backlog buildup."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from utils.structured_log import log_event

logger = __import__("logging").getLogger(__name__)


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def wire_recovery_enabled() -> bool:
    if not _env_bool("WIRE_RECOVERY_ENABLED", "true"):
        return False
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        return news_channel_beat_enabled()
    except Exception:
        return False


def wire_silence_alert_minutes() -> float:
    return _env_float("WIRE_SILENCE_ALERT_MINUTES", 25.0, lo=10.0, hi=120.0)


def wire_early_recovery_minutes() -> float:
    """Silence after which wire bypasses source cooldowns and early governance relax kicks in."""
    return _env_float("WIRE_EARLY_RECOVERY_MINUTES", 15.0, lo=5.0, hi=60.0)


def wire_recovery_silence_minutes() -> float:
    return _env_float("WIRE_RECOVERY_SILENCE_MINUTES", 45.0, lo=15.0, hi=360.0)


def wire_recovery_backlog_threshold() -> int:
    return _env_int("WIRE_RECOVERY_BACKLOG_THRESHOLD", 400, lo=50, hi=10000)


def wire_early_recovery_active(*, silence_min: float | None = None) -> bool:
    if not wire_recovery_enabled():
        return False
    sm = silence_min if silence_min is not None else minutes_since_last_publish()
    if sm is not None and sm >= wire_early_recovery_minutes():
        return True
    return False


def wire_bypass_diversity_cooldowns() -> bool:
    if not wire_recovery_enabled():
        return False
    if not _env_bool("WIRE_BYPASS_SOURCE_COOLDOWN", "true"):
        return False
    try:
        from scheduler.runtime_context import get_pipeline_context

        ctx = get_pipeline_context()
        if ctx and getattr(ctx, "wire_recovery_active", False):
            return True
    except Exception:
        pass
    if wire_early_recovery_active():
        return True
    return wire_throughput_recovery_active()


def wire_bypass_suppression_memory() -> bool:
    """Bypass suppression_ttl / suppression_memory during wire silence recovery."""
    if not wire_recovery_enabled():
        return False
    if not _env_bool("WIRE_BYPASS_SUPPRESSION_TTL", "true"):
        return False
    try:
        from scheduler.runtime_context import get_pipeline_context

        ctx = get_pipeline_context()
        if ctx and getattr(ctx, "wire_recovery_active", False):
            return True
    except Exception:
        pass
    silence = minutes_since_last_publish()
    if silence is not None and silence >= wire_silence_alert_minutes():
        return True
    return wire_throughput_recovery_active()


def minutes_since_last_publish() -> float | None:
    try:
        from app.editorial.desk_starvation import hours_since_last_publish

        hours = hours_since_last_publish()
        if hours is None:
            return None
        return hours * 60.0
    except Exception:
        return None


async def count_unprocessed_raw_posts() -> int:
    from sqlalchemy import func, select

    from db.models import RawPost
    from db.session import session_scope

    async with session_scope() as session:
        return int(
            (await session.execute(select(func.count()).select_from(RawPost).where(RawPost.processed_at.is_(None)))).scalar()
            or 0
        )


def wire_throughput_recovery_active(*, backlog: int | None = None, silence_min: float | None = None) -> bool:
    """True when wire must prioritize throughput over diversity/growth gates."""
    if not wire_recovery_enabled():
        return False
    sm = silence_min if silence_min is not None else minutes_since_last_publish()
    if sm is not None and sm >= wire_recovery_silence_minutes():
        return True
    if sm is None:
        return True
    if backlog is not None and backlog >= wire_recovery_backlog_threshold():
        return True
    try:
        from app.editorial.stability.anti_pause import evaluate_anti_pause

        ap = evaluate_anti_pause()
        if ap.anti_pause_active or ap.max_gap_exceeded:
            return True
    except Exception:
        pass
    return False


def wire_bypass_rumor_single_source(*, sources: list[str] | None = None) -> bool:
    """Allow tier-1/fastlane single-source items through final gate during wire recovery."""
    if not wire_recovery_enabled():
        return False
    if not _env_bool("WIRE_BYPASS_RUMOR_SINGLE_SOURCE", "true"):
        return False
    if wire_early_recovery_active() or wire_throughput_recovery_active():
        return True
    chans = [str(c or "").strip().lower() for c in (sources or []) if str(c or "").strip()]
    if not chans:
        return False
    try:
        from app.editorial.source_tiers import aggregate_source_tier
        from app.ops.autonomous_publish import _auto_publish_fastlane_sources

        tier_info = aggregate_source_tier(chans)
        if tier_info.tier <= 2:
            return True
        fastlane = _auto_publish_fastlane_sources()
        dom = max(set(chans), key=chans.count)
        dom_key = dom.lstrip("@")
        if dom in fastlane or dom_key in fastlane:
            return True
    except Exception:
        pass
    return False


def wire_should_fail_blocked_draft(reason: str) -> bool:
    """Fail approved drafts blocked on recoverable gates so publish queue advances."""
    if not wire_recovery_enabled():
        return False
    if reason not in {"rumor_single_source"}:
        return False
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        if not news_channel_beat_enabled():
            return False
        if not _env_bool("EDITORIAL_ZERO_HUMAN_IN_LOOP", "false"):
            return False
    except Exception:
        return False
    return True


async def wire_recovery_snapshot() -> dict[str, Any]:
    backlog = await count_unprocessed_raw_posts()
    silence = minutes_since_last_publish()
    full = wire_throughput_recovery_active(backlog=backlog, silence_min=silence)
    early = wire_early_recovery_active(silence_min=silence)
    active = full or early
    return {
        "active": active,
        "early_recovery": early,
        "full_recovery": full,
        "backlog_unprocessed": backlog,
        "silence_minutes": round(silence, 1) if silence is not None else None,
        "backlog_threshold": wire_recovery_backlog_threshold(),
        "silence_threshold_min": wire_recovery_silence_minutes(),
        "early_recovery_min": wire_early_recovery_minutes(),
    }


def apply_wire_recovery_env_boost() -> list[str]:
    """Temporary runtime env relaxation during recovery (idempotent)."""
    if not wire_throughput_recovery_active():
        return []
    changed: list[str] = []
    boosts = {
        "UEOS_PUBLISH_THRESHOLD": str(max(58, int(float(os.getenv("UEOS_PUBLISH_THRESHOLD", "68")) - 4))),
        "PUBLISH_FLOOR_MAX_SILENCE_MIN": str(min(18, int(float(os.getenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "22"))))),
        "DESK_STARVATION_HOURS": str(min(1.5, float(os.getenv("DESK_STARVATION_HOURS", "6") or "6"))),
    }
    for key, val in boosts.items():
        cur = os.getenv(key, "").strip()
        if cur != val:
            os.environ[key] = val
            changed.append(f"{key}={val}")
    return changed


_alert_last_ts: float = 0.0


async def maybe_alert_wire_silence(bot: Any, settings: Any) -> dict[str, Any]:
    """Notify operator once per hour when channel silence exceeds wire alert threshold."""
    global _alert_last_ts
    result: dict[str, Any] = {"alerted": False}
    if not wire_recovery_enabled():
        return result

    silence = minutes_since_last_publish()
    if silence is None or silence < wire_silence_alert_minutes():
        return result

    now = time.time()
    if now - _alert_last_ts < 3600:
        return result

    admin_id = int(getattr(settings, "admin_user_id", 0) or 0)
    if not bot or not admin_id:
        return result

    snap = await wire_recovery_snapshot()
    boosts = apply_wire_recovery_env_boost()
    text = (
        f"⚠️ Wire silence {silence:.0f} min\n"
        f"Backlog: {snap.get('backlog_unprocessed')} raw\n"
        f"Recovery: {'ON' if snap.get('active') else 'off'}"
    )
    if boosts:
        text += f"\nAuto-boost: {', '.join(boosts[:3])}"

    try:
        await bot.send_message(admin_id, text[:3900], disable_web_page_preview=True)
        _alert_last_ts = now
        result["alerted"] = True
        log_event(logger, "wire_recovery.silence_alert", silence_min=silence, backlog=snap.get("backlog_unprocessed"))
    except Exception as exc:
        log_event(logger, "wire_recovery.alert_failed", error=repr(exc)[:160])

    return result
