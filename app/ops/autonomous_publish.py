"""Unattended auto-approve / auto-publish policy (observable, non-blocking)."""

from __future__ import annotations

import json
import logging
import os
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
) -> tuple[bool, str]:
    """
    Return (approved, reason_code).
    Quality failures return False with explicit reason — never silent.
    """
    if not auto_publish_enabled():
        return False, "auto_publish_disabled"

    text = (content or "").strip()
    try:
        from app.ops.controlled_rollout import effective_auto_publish_min_text_chars

        min_len = effective_auto_publish_min_text_chars()
    except Exception:
        min_len = int(os.getenv("AUTO_PUBLISH_MIN_TEXT_CHARS", "80").strip() or "80")
    if len(text) < min_len:
        return False, "quality_text_too_short"

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
    if conf < _min_confidence():
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
        pending = await list_pending_drafts(session, limit=3)
        for draft in pending:
            ok, reason = evaluate_draft_for_auto_publish(
                draft_id=int(draft.id),
                content=str(draft.content or ""),
                extras_json=str(draft.extras or ""),
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
                )
                return did
        return None
    except Exception as exc:
        log_event(logger, "auto_publish_rejected", reason="error", error=repr(exc)[:200])
        return None
