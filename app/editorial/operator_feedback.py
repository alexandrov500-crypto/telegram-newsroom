"""Structured operator feedback — advisory integration only (no publish bypass)."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class FeedbackAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    RETRY = "retry"
    PRIORITIZE_TOPIC = "prioritize_topic"
    DEPRIORITIZE_TOPIC = "deprioritize_topic"
    SUPPRESS_SOURCE = "suppress_source"
    TRUSTED_SOURCE = "trusted_source"
    STYLE_ADJUSTMENT = "style_adjustment"
    DUPLICATE_MARK = "duplicate_mark"
    FALSE_POSITIVE_MARK = "false_positive_mark"


_PUBLISH_BYPASS_ACTIONS = frozenset()


def _valid_action(raw: str) -> FeedbackAction | None:
    try:
        return FeedbackAction(str(raw).strip().lower())
    except ValueError:
        return None


async def receive_operator_feedback(
    *,
    settings: Any,
    operator_id: int,
    action: str,
    tick_id: str = "",
    draft_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[int | None, str]:
    """
    Persist feedback and apply advisory side-effects. Returns (feedback_id, status).
  Never bypasses execution graph or publish gates.
    """
    act = _valid_action(action)
    if act is None:
        log_event(
            logger,
            "operator_feedback_rejected",
            action=action,
            reason="unknown_action",
            operator_id=operator_id,
        )
        return None, "rejected:unknown_action"

    if act in _PUBLISH_BYPASS_ACTIONS:
        log_event(logger, "operator_feedback_rejected", action=act.value, reason="publish_bypass_forbidden")
        return None, "rejected:publish_bypass_forbidden"

    from db.operator_feedback_repository import insert_operator_feedback

    fid = await insert_operator_feedback(
        operator_id=operator_id,
        action=act.value,
        tick_id=tick_id,
        draft_id=draft_id,
        metadata=metadata,
    )
    log_event(
        logger,
        "operator_feedback_received",
        feedback_id=fid,
        action=act.value,
        operator_id=operator_id,
        tick_id=tick_id or "",
        draft_id=draft_id,
    )

    ok, reason = await _apply_advisory(settings, act, metadata=metadata or {}, draft_id=draft_id)
    if ok:
        from db.operator_feedback_repository import mark_feedback_applied

        await mark_feedback_applied(fid, reason=reason)
        log_event(
            logger,
            "operator_feedback_applied",
            feedback_id=fid,
            action=act.value,
            reason=reason,
        )
    else:
        log_event(
            logger,
            "operator_feedback_rejected",
            feedback_id=fid,
            action=act.value,
            reason=reason,
        )
    return fid, "applied" if ok else f"rejected:{reason}"


async def _apply_advisory(
    settings: Any,
    action: FeedbackAction,
    *,
    metadata: dict[str, Any],
    draft_id: int | None,
) -> tuple[bool, str]:
    rd = settings.runtime_state_dir
    meta = metadata

    if action == FeedbackAction.APPROVE:
        return True, "logged_approve_hint"

    if action == FeedbackAction.REJECT:
        chans = meta.get("channels") or []
        if isinstance(chans, list) and chans:
            from utils.source_reputation import record_reject_for_channels

            record_reject_for_channels([str(c) for c in chans if c], runtime_dir=rd)
        return True, "reject_hint_recorded"

    if action == FeedbackAction.RETRY:
        return True, "retry_hint_only_no_auto_publish"

    if action == FeedbackAction.SUPPRESS_SOURCE:
        ch = str(meta.get("channel") or meta.get("source") or "").strip()
        if not ch:
            return False, "missing_channel"
        from editorial.governance.operator_controls import suppress_source

        suppress_source(rd, ch, reason=str(meta.get("reason") or "operator_feedback"))
        return True, "source_suppressed"

    if action == FeedbackAction.TRUSTED_SOURCE:
        ch = str(meta.get("channel") or meta.get("source") or "").strip()
        if not ch:
            return False, "missing_channel"
        from editorial.governance.operator_controls import boost_source

        boost_source(rd, ch, boost=float(meta.get("boost") or 0.1), reason="operator_trusted_source")
        return True, "source_boosted"

    if action == FeedbackAction.PRIORITIZE_TOPIC:
        topic = str(meta.get("topic") or meta.get("topic_key") or "").strip().lower()
        if not topic:
            return False, "missing_topic"
        _set_topic_boost(rd, topic, boost=float(meta.get("boost") or 0.08))
        return True, "topic_prioritized"

    if action == FeedbackAction.DEPRIORITIZE_TOPIC:
        topic = str(meta.get("topic") or meta.get("topic_key") or "").strip().lower()
        if not topic:
            return False, "missing_topic"
        from editorial.governance.operator_controls import mute_topic

        mute_topic(rd, topic, ttl_sec=float(meta.get("ttl_sec") or 3600), reason="operator_deprioritize")
        return True, "topic_deprioritized"

    if action == FeedbackAction.DUPLICATE_MARK:
        chans = meta.get("channels") or []
        if isinstance(chans, list):
            from utils.source_reputation import record_duplicate_signal_for_channels

            record_duplicate_signal_for_channels([str(c) for c in chans if c], runtime_dir=rd)
        return True, "duplicate_mark_recorded"

    if action == FeedbackAction.FALSE_POSITIVE_MARK:
        return True, "false_positive_logged"

    if action == FeedbackAction.STYLE_ADJUSTMENT:
        _append_style_hint(rd, meta)
        return True, "style_hint_stored"

    return False, "unhandled"


def _set_topic_boost(runtime_dir: str, topic: str, *, boost: float) -> None:
    from editorial.governance.operator_controls import get_operator_controls, reload_operator_controls
    from editorial.intelligence_store import save_json
    from editorial.governance.paths import operator_controls_path

    data = get_operator_controls(runtime_dir)
    boosts = dict(data.get("topic_boosts") or {})
    boosts[topic[:80]] = {"boost": max(-0.2, min(0.25, float(boost))), "reason": "operator_feedback"}
    data["topic_boosts"] = boosts
    save_json(operator_controls_path(runtime_dir), data)
    reload_operator_controls(runtime_dir)


def _append_style_hint(runtime_dir: str, meta: dict[str, Any]) -> None:
    from pathlib import Path

    path = Path(runtime_dir) / "operator_style_hints.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(
        json.dumps(meta, ensure_ascii=False, default=str) + "\n"
    )


def publish_gate_hint_from_feedback(runtime_dir: str, *, draft_id: int | None = None) -> dict[str, Any]:
    """Advisory hints only — publish gates remain authoritative."""
    return {"advisory": True, "draft_id": draft_id, "operator_controls": True}
