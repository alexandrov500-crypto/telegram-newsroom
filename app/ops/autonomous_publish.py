"""Unattended auto-approve / auto-publish policy (observable, non-blocking)."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _min_confidence() -> float:
    try:
        from app.ops.controlled_rollout import effective_auto_publish_min_confidence

        return effective_auto_publish_min_confidence()
    except Exception:
        pass
    raw = os.getenv("AUTO_PUBLISH_MIN_CONFIDENCE", "0.72").strip()
    try:
        return max(0.5, min(0.99, float(raw)))
    except ValueError:
        return 0.72


def _allowed_categories() -> frozenset[str] | None:
    raw = os.getenv("AUTO_PUBLISH_ALLOWED_CATEGORIES", "").strip()
    if not raw:
        return None
    return frozenset(p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip())


def _auto_publish_fastlane_sources() -> frozenset[str]:
    raw = os.getenv("AUTO_PUBLISH_FASTLANE_SOURCES", "@cb_economics").strip()
    out: set[str] = set()
    for p in raw.replace(";", ",").split(","):
        s = p.strip().lower()
        if not s:
            continue
        out.add(s if s.startswith("@") else f"@{s}")
        out.add(s.lstrip("@"))
    return frozenset(out)


def _dominant_source_from_sources_json(sources_json: str | None) -> str:
    if not sources_json:
        return ""
    try:
        data = json.loads(sources_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, list):
        return ""
    counts: dict[str, int] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        ch = str(row.get("channel") or "").strip().lower()
        if not ch:
            continue
        key = ch if ch.startswith("@") else f"@{ch.lstrip('@')}"
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return ""
    return max(counts.keys(), key=lambda k: (counts[k], k))


def _channels_from_sources_json(sources_json: str | None) -> list[str]:
    if not sources_json:
        return []
    try:
        data = json.loads(sources_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        ch = str(row.get("channel") or "").strip()
        if ch:
            out.append(ch)
    return out


def _backlog_relief_enabled() -> bool:
    return _env_bool("AUTO_PUBLISH_BACKLOG_RELIEF_ENABLED", "true")


def _backlog_relief_min_signal() -> float:
    raw = os.getenv("AUTO_PUBLISH_BACKLOG_RELIEF_MIN_SIGNAL", "0.62").strip()
    try:
        return max(0.5, min(0.9, float(raw)))
    except ValueError:
        return 0.62


def _stall_thresholds() -> tuple[float, float]:
    # Low: <20m (no action), Medium: 20-45m, High: >=45m.
    return 20.0, 45.0


def _is_active_market_session(*, newsroom_tz: str | None = None) -> bool:
    try:
        from app.editorial.growth_cadence import resolve_cadence_session

        sess = resolve_cadence_session(newsroom_tz=newsroom_tz)
        return sess.key != "offhours"
    except Exception:
        return True


def _recent_narrative_momentum(runtime_dir: str | None) -> float:
    if not runtime_dir:
        return 0.5
    try:
        from app.editorial.intelligence.trend_memory import trend_memory_events

        ev = trend_memory_events(runtime_dir, hours=24)
        if not ev:
            return 0.5
        vals = []
        for e in ev:
            rep = float(e.get("repost_rate") or 0.0)
            fwd = float(e.get("forward_velocity") or 0.0)
            vals.append(rep * 0.55 + fwd * 0.45)
        return round(min(1.0, max(0.0, sum(vals) / max(1, len(vals)))), 4)
    except Exception:
        return 0.5


async def detect_publish_stall_risk(settings: Any, session: Any) -> dict[str, Any]:
    from db.models import Draft, RawPost
    from sqlalchemy import func, select

    low_m, high_m = _stall_thresholds()
    pending_backlog = int(
        (
            await session.execute(select(func.count()).select_from(Draft).where(Draft.status == "pending"))
        ).scalar_one()
        or 0
    )
    last_published = await session.scalar(
        select(Draft.created_at).where(Draft.status == "published").order_by(Draft.created_at.desc()).limit(1)
    )
    minutes_since = 10_000.0
    if last_published is not None:
        dt = last_published
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=UTC)
        minutes_since = max(0.0, (datetime.now(UTC) - dt.astimezone(UTC)).total_seconds() / 60.0)
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    incoming_raw_flow = int(
        (
            await session.execute(
                select(func.count()).select_from(RawPost).where(RawPost.created_at >= cutoff)
            )
        ).scalar_one()
        or 0
    )
    active_market_session = _is_active_market_session(newsroom_tz=getattr(settings, "newsroom_timezone", None))
    narrative_momentum = _recent_narrative_momentum(getattr(settings, "runtime_state_dir", None))

    if minutes_since < low_m:
        level = "low"
    elif minutes_since < high_m and active_market_session and pending_backlog >= 2 and incoming_raw_flow >= 1:
        level = "medium"
    elif minutes_since >= high_m and pending_backlog >= 3:
        level = "high"
    else:
        level = "low"
    should_recover = level in {"medium", "high"}
    return {
        "level": level,
        "minutes_since_last_published": round(minutes_since, 2),
        "pending_backlog": pending_backlog,
        "incoming_raw_flow_30m": incoming_raw_flow,
        "active_market_session": active_market_session,
        "narrative_momentum": narrative_momentum,
        "should_recover": should_recover,
    }


def auto_publish_enabled() -> bool:
    if settings_force_manual():
        return False
    try:
        import os
        from app.observability.publish_continuity import is_operator_autopublish_paused

        rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
        if is_operator_autopublish_paused(rd):
            return False
    except Exception:
        pass
    try:
        from app.observability.runtime_protection import autonomous_publish_blocked

        if autonomous_publish_blocked():
            return False
    except Exception:
        pass
    try:
        from app.ops.public_incident_safety import incident_frozen

        if incident_frozen():
            return False
    except Exception:
        pass
    try:
        from app.ops.live_rollback import rollback_active

        if rollback_active():
            return False
    except Exception:
        pass
    try:
        from app.ops.controlled_rollout import rollout_auto_publish_allowed

        ok, _reason = rollout_auto_publish_allowed()
        if not ok:
            return False
    except Exception:
        pass
    return _env_bool("AUTO_PUBLISH_ENABLED", "false") or _env_bool("AUTO_APPROVE_DRAFTS", "false")


def settings_force_manual() -> bool:
    if _env_bool("LIVE_SUPERVISED_APPROVAL", "false"):
        return True
    if _env_bool("FINAL_STAGING_MODE", "false") and not _env_bool("AUTO_PUBLISH_ENABLED", "false"):
        return True
    return False


def evaluate_draft_for_auto_publish(
    *,
    draft_id: int,
    content: str,
    extras_json: str | None,
    sources_json: str | None = None,
    runtime_dir: str | None = None,
    backlog_relief: bool = False,
    stall_level: str = "low",
) -> tuple[bool, str]:
    """
    Return (approved, reason_code).
    Quality failures return False with explicit reason — never silent.
    """
    if not auto_publish_enabled():
        return False, "auto_publish_disabled"

    text = (content or "").strip()
    dominant_source = _dominant_source_from_sources_json(sources_json)
    if dominant_source:
        src_key = dominant_source.lower()
        fastlane = _auto_publish_fastlane_sources()
        if src_key in fastlane or src_key.lstrip("@") in fastlane:
            from app.editorial.content_quality import is_publishably_informative

            if not is_publishably_informative(text, min_chars=60, min_sentences=2):
                return False, "quality_not_informative"
            if text.count("{") + text.count("```") > 4:
                return False, "quality_debug_markers"
            return True, f"source_fastlane:{dominant_source}"

    try:
        from app.ops.controlled_rollout import effective_auto_publish_min_text_chars

        min_len = effective_auto_publish_min_text_chars()
    except Exception:
        min_len = int(os.getenv("AUTO_PUBLISH_MIN_TEXT_CHARS", "80").strip() or "80")
    if len(text) < min_len:
        return False, "quality_text_too_short"

    from app.editorial.content_quality import is_publishably_informative

    if not is_publishably_informative(text, min_chars=max(60, min_len), min_sentences=2):
        return False, "quality_not_informative"

    if text.count("{") + text.count("```") > 4:
        return False, "quality_debug_markers"

    detail: dict[str, Any] = {}
    if extras_json:
        try:
            detail = json.loads(extras_json)
        except (json.JSONDecodeError, TypeError):
            detail = {}
    if not isinstance(detail, dict):
        detail = {}

    allowed = _allowed_categories()
    gov = detail.get("editorial_governance") or detail.get("cluster_intelligence") or {}
    if isinstance(gov, dict):
        cat = str(gov.get("editorial_category") or gov.get("topic_hint") or "").strip().lower()
        if allowed and cat and cat not in allowed:
            return False, f"category_not_allowed:{cat[:40]}"

    conf_block = detail.get("editorial_confidence") or {}
    conf = 0.0
    if isinstance(conf_block, dict):
        try:
            conf = float(
                conf_block.get("confidence_score")
                or conf_block.get("total")
                or conf_block.get("score")
                or 0.0
            )
        except (TypeError, ValueError):
            conf = 0.0
    conf_low = conf < _min_confidence()
    if conf_low and not (backlog_relief and _backlog_relief_enabled()):
        return False, f"confidence_below_min:{conf:.2f}"

    dup = detail.get("duplicate_intel") or {}
    if isinstance(dup, dict):
        try:
            sim = float(dup.get("max_similarity_pct") or 0.0)
            if sim >= float(os.getenv("AUTO_PUBLISH_MAX_DUPLICATE_PCT", "85")):
                return False, f"duplicate_similarity:{sim:.0f}"
        except (TypeError, ValueError):
            pass

    hold = bool(detail.get("editorial_hold")) or (
        isinstance(gov, dict) and gov.get("editorial_hold")
    )
    if hold:
        return False, "operator_review_required"

    if backlog_relief and _backlog_relief_enabled():
        try:
            from app.editorial.content_quality import has_hidden_advertising, passes_premium_newsroom_policy
            from app.editorial.intelligence.trend_memory import evaluate_narrative_strategy
            from app.editorial.scoring_engine import score_story
            from app.editorial.signal_ranking import rank_story_signal
            from app.editorial.source_tiers import aggregate_source_tier

            channels = _channels_from_sources_json(sources_json)
            tier_info = aggregate_source_tier(channels, runtime_dir=runtime_dir)
            dominant_source = _dominant_source_from_sources_json(sources_json)
            fastlane = _auto_publish_fastlane_sources()
            tier1_equiv = tier_info.tier == 1 or (
                dominant_source and (dominant_source in fastlane or dominant_source.lstrip("@") in fastlane)
            )
            escore = score_story(text=text, sources=channels, runtime_dir=runtime_dir)
            category = str(detail.get("category") or (detail.get("editorial_tags") or {}).get("category") or "macro")
            signal = rank_story_signal(
                text,
                escore,
                sources=channels,
                runtime_dir=runtime_dir,
                category=category,
            )
            trend = evaluate_narrative_strategy(runtime_dir or "var/runtime", text=text, category=category)
            trend_status = str(trend.get("status") or "stable")
            narrative_continuation = bool(trend.get("open_loop_continuation", True)) and trend_status in {"winning", "stable"}
            try:
                sim = float((detail.get("duplicate_intel") or {}).get("max_similarity_pct") or 0.0)
            except (TypeError, ValueError):
                sim = 0.0
            if stall_level == "medium":
                tier_ok = tier1_equiv
            elif stall_level == "high":
                tier_ok = tier_info.tier <= 2
            else:
                tier_ok = False
            # Controlled backlog relief: only trusted sources and clean high-signal narratives.
            if (
                tier_ok
                and signal.signal_score >= _backlog_relief_min_signal()
                and not signal.reject_reason
                and not signal.manual_review_hint
                and signal.forwardability >= 0.58
                and signal.fatigue_probability <= 0.68
                and escore.relevance_score >= 0.35
                and narrative_continuation
                and sim < float(os.getenv("AUTO_PUBLISH_MAX_DUPLICATE_PCT", "85"))
                and not has_hidden_advertising(text)
                and passes_premium_newsroom_policy(text)
            ):
                return (
                    True,
                    f"backlog_relief_{stall_level}_tier{tier_info.tier}:{signal.signal_score:.2f}:{signal.forwardability:.2f}",
                )
        except Exception:
            pass

    if conf_low:
        return False, f"confidence_below_min:{conf:.2f}"
    return True, "auto_publish_approved"


async def try_auto_schedule_one_pending(settings: Any, session: Any) -> int | None:
    """
    Approve + schedule one pending draft if policy allows.
    Returns draft_id or None. Never raises.
    """
    from db.repository import approve_draft, list_pending_drafts, schedule_draft_publish, utcnow

    if not auto_publish_enabled():
        log_event(logger, "auto_publish_rejected", reason="disabled")
        return None
    try:
        pending_limit = 3
        backlog_relief = False
        stall = {"level": "low", "should_recover": False}
        try:
            stall = await detect_publish_stall_risk(settings, session)
            backlog_relief = _backlog_relief_enabled() and bool(stall.get("should_recover"))
            if backlog_relief:
                pending_limit = 12 if str(stall.get("level")) == "high" else 6
                log_event(
                    logger,
                    "auto_publish.backlog_relief_mode",
                    stall_level=stall.get("level"),
                    pending_backlog=stall.get("pending_backlog"),
                    minutes_since_last_published=stall.get("minutes_since_last_published"),
                    incoming_raw_flow_30m=stall.get("incoming_raw_flow_30m"),
                    active_market_session=stall.get("active_market_session"),
                    narrative_momentum=stall.get("narrative_momentum"),
                )
        except Exception:
            backlog_relief = False
        pending = await list_pending_drafts(session, limit=pending_limit)
        for draft in pending:
            ok, reason = evaluate_draft_for_auto_publish(
                draft_id=int(draft.id),
                content=str(draft.content or ""),
                extras_json=str(getattr(draft, "draft_extras", None) or getattr(draft, "extras", None) or "{}"),
                sources_json=str(getattr(draft, "sources", None) or "[]"),
                runtime_dir=getattr(settings, "runtime_state_dir", None),
                backlog_relief=backlog_relief,
                stall_level=str(stall.get("level") or "low"),
            )
            if not ok:
                log_event(
                    logger,
                    "auto_publish_rejected",
                    draft_id=int(draft.id),
                    reason=reason,
                )
                continue
            did = int(draft.id)
            if await approve_draft(session, did):
                await schedule_draft_publish(session, did, when=utcnow())
                log_event(
                    logger,
                    "auto_publish_approved",
                    draft_id=did,
                    reason=reason,
                    stall_level=stall.get("level"),
                    pending_backlog=stall.get("pending_backlog"),
                    incoming_raw_flow_30m=stall.get("incoming_raw_flow_30m"),
                    narrative_momentum=stall.get("narrative_momentum"),
                )
                return did
        return None
    except Exception as exc:
        log_event(logger, "auto_publish_rejected", reason="error", error=repr(exc)[:200])
        return None


def _floor_max_silence_min() -> float:
    """Hard silence ceiling: after this, the publishing floor forces a post."""
    raw = os.getenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "90").strip()
    try:
        return max(30.0, min(720.0, float(raw)))
    except ValueError:
        return 90.0


def _floor_enabled() -> bool:
    return _env_bool("PUBLISH_FLOOR_ENABLED", "true")


async def select_floor_publish_candidate(settings: Any, session: Any) -> dict[str, Any] | None:
    """Guaranteed publishing floor.

    When the channel has been silent past the hard ceiling, pick the best
    *trustworthy* pending draft to force-publish in safety-only mode. This is
    intentionally independent of the experimental ranking/quality stack so that
    no algorithm change can keep the channel silent. Safety is still enforced
    downstream by the safety-only final gate (advertising, governance, trust).

    Returns ``{"draft_id": int, "minutes_since": float, ...}`` or ``None``.
    """
    if not _floor_enabled() or not auto_publish_enabled():
        return None
    try:
        from app.editorial.content_quality import has_hidden_advertising, is_publishably_informative
        from app.publisher.draft_builder import polish_channel_post
        from db.repository import list_pending_drafts, list_recent_quality_failed_drafts

        stall = await detect_publish_stall_risk(settings, session)
        minutes_since = float(stall.get("minutes_since_last_published") or 0.0)
        if minutes_since < _floor_max_silence_min():
            return None
        pending = await list_pending_drafts(session, limit=25)
        # Fall back to the freshest quality-failed drafts (e.g. OpenAI down →
        # rule-fallback summaries judged "low-signal") so the channel never goes
        # dark when no clean pending draft exists. Safety is re-checked by the
        # safety-only final gate at publish time.
        quality_failed = await list_recent_quality_failed_drafts(session, limit=15)
        # Most recent first; prefer fresh pending over reopened failed drafts.
        candidates = sorted(
            list(pending) + list(quality_failed),
            key=lambda d: int(getattr(d, "id", 0)),
            reverse=True,
        )
        if not candidates:
            return None
        seen: set[int] = set()
        for draft in candidates:
            did = int(getattr(draft, "id", 0))
            if did in seen:
                continue
            seen.add(did)
            body = polish_channel_post(str(draft.content or ""), max_chars=8000)
            if not body or has_hidden_advertising(body):
                continue
            if not is_publishably_informative(body, min_chars=80, min_sentences=1):
                continue
            return {
                "draft_id": did,
                "minutes_since": round(minutes_since, 2),
                "pending_backlog": stall.get("pending_backlog"),
                "incoming_raw_flow_30m": stall.get("incoming_raw_flow_30m"),
            }
        return None
    except Exception as exc:
        log_event(logger, "publish_floor.select_failed", error=repr(exc)[:200])
        return None
