"""Production priority router: FAST / STANDARD / SLOW lanes (Reuters hot path)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from app.editorial.gatekeeper import (
    apply_gate_boost,
    evaluate_editorial_gate,
    log_editorial_drop,
    persist_gate_rejection,
)
from app.editorial.ranking import score_item
from app.editorial.scoring_engine import score_story
from app.editorial.suppression import should_suppress
from app.ops.queues import Lane, get_lane_queues, init_lane_queues, sync_legacy_worker_queues
from app.observability import ops_metrics as om

logger = logging.getLogger(__name__)

_FAST_KW = re.compile(
    r"\b(war|ban|banned|sanctions|санкци|hack|hacked|breaking|resign|"
    r"collapse|войн|взрыв|urgent|срочно|default|shutdown)\b",
    re.I,
)

_FAST_URGENCY = float(os.getenv("FAST_LANE_URGENCY_MIN", "0.85"))
_FAST_LATENCY_TARGET_SEC = float(os.getenv("FAST_LANE_LATENCY_TARGET_SEC", "5"))


@dataclass(frozen=True)
class RoutingDecision:
    lane: Lane
    reason: str
    urgency: float
    breaking: bool
    final_score: float
    dropped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ops_lanes_enabled() -> bool:
    env_on = os.getenv("FAST_LANE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not env_on:
        return False
    from app.ops.control_plane.guards import emergency_halt_active

    return not emergency_halt_active()


def breaking_override_mode() -> bool:
    return os.getenv("BREAKING_OVERRIDE", "false").strip().lower() in {"1", "true", "yes", "on"}


def breaking_only_mode() -> bool:
    return os.getenv("BREAKING_ONLY_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("news_id") or item.get("ingest_key") or item.get("message_id") or "?")


def _runtime_dir(item: dict[str, Any]) -> str | None:
    return item.get("runtime_dir") or os.getenv("RUNTIME_STATE_DIR", "var/runtime")


def _keyword_hit(text: str) -> str | None:
    m = _FAST_KW.search(text or "")
    return f"keyword:{m.group(0).lower()}" if m else None


def _freshness_sec(item: dict[str, Any]) -> float:
    ts = item.get("ingested_at_unix")
    if ts is None:
        return 0.0
    return max(0.0, time.time() - float(ts))


def classify_lane(item: dict[str, Any], *, rank: Any, escore: Any) -> RoutingDecision:
    text = str(item.get("text") or "")
    urgency = float(getattr(escore, "urgency_score", 0.0))
    breaking = bool(getattr(escore, "is_breaking", False)) or float(getattr(rank, "breaking", 0.0)) >= 0.75
    final = float(getattr(rank, "final_score", 0.0))
    sources = item.get("confirmed_sources") or item.get("sources") or []
    source_count = len(sources) if isinstance(sources, list) else 1
    fresh = _freshness_sec(item)

    if breaking_override_mode():
        return RoutingDecision(Lane.FAST, "breaking_override_env", urgency, True, final)

    kw = _keyword_hit(text)
    if breaking:
        return RoutingDecision(Lane.FAST, "breaking_flag", urgency, True, final)
    if urgency >= _FAST_URGENCY:
        return RoutingDecision(Lane.FAST, f"urgency>={_FAST_URGENCY}", urgency, breaking, final)
    if source_count >= 2 and fresh < 180:
        return RoutingDecision(Lane.FAST, "multi_source_fresh", urgency, breaking, final)
    if kw:
        return RoutingDecision(Lane.FAST, kw, urgency, breaking, final)

    if final >= 0.45 or float(getattr(escore, "final_priority_score", 0.0)) >= 55:
        return RoutingDecision(Lane.STANDARD, "standard_editorial_score", urgency, breaking, final)
    return RoutingDecision(Lane.SLOW, "low_priority_background", urgency, breaking, final)


def _log_fast_lane(item: dict[str, Any], decision: RoutingDecision) -> None:
    logger.info(
        "[FAST_LANE] msg_id=%s urgency=%.2f reason=%s latency_target=%ss",
        _item_id(item),
        decision.urgency,
        decision.reason,
        int(_FAST_LATENCY_TARGET_SEC),
    )


def _log_route(lane: Lane, item: dict[str, Any], decision: RoutingDecision, *, escalated: str | None = None) -> None:
    if lane == Lane.FAST:
        _log_fast_lane(item, decision)
        return
    msg = (
        f"[ROUTE] lane={lane.value.upper()} msg_id={_item_id(item)} "
        f"reason={decision.reason} score={decision.final_score:.2f}"
    )
    if escalated:
        msg += f" escalated={escalated}"
    logger.info(msg)


def _enqueue_with_escalation(item: dict[str, Any], decision: RoutingDecision) -> RoutingDecision | None:
    reg = get_lane_queues()
    if reg is None:
        return None

    order = [decision.lane, Lane.STANDARD, Lane.SLOW]
    if decision.lane == Lane.STANDARD:
        order = [Lane.STANDARD, Lane.SLOW]
    elif decision.lane == Lane.SLOW:
        order = [Lane.SLOW]

    enriched = {**item, "ops_lane": decision.lane.value, "ops_route_reason": decision.reason}
    from app.ops.control_plane.guards import queue_depth_over_cap

    depths = reg.depths()
    if queue_depth_over_cap(
        fast=int(depths.get("fast", 0)),
        standard=int(depths.get("standard", 0)),
        slow=int(depths.get("slow", 0)),
    ):
        om.record_overflow(decision.lane.value)
        logger.warning("[ROUTE] DROP msg_id=%s reason=max_queue_depth", _item_id(item))
        from app.ops.ledger.writer import record_dropped

        record_dropped(item, reason="max_queue_depth")
        return RoutingDecision(decision.lane, "dropped_max_depth", decision.urgency, decision.breaking, decision.final_score, dropped=True)

    for idx, lane in enumerate(order):
        q = reg.get(lane)
        if q.push_nowait(enriched):
            om.record_routing_decision(lane.value)
            _log_route(lane, enriched, decision, escalated=None if idx == 0 else f"{decision.lane.value}_full")
            om.record_queue_depths(**reg.depths())
            return RoutingDecision(lane, decision.reason, decision.urgency, decision.breaking, decision.final_score)

    om.record_overflow(decision.lane.value)
    logger.warning("[ROUTE] DROP msg_id=%s reason=all_lanes_full", _item_id(item))
    from app.ops.ledger.writer import record_dropped

    record_dropped(item, reason="all_lanes_full")
    om.record_queue_depths(**reg.depths())
    return RoutingDecision(decision.lane, "dropped_overflow", decision.urgency, decision.breaking, decision.final_score, dropped=True)


def route_message_event(item: dict[str, Any]) -> RoutingDecision | None:
    """
    Full ops path: gate → suppress → score → classify → enqueue.
    Returns None if rejected before routing.
    """
    from app.ops.control_plane.guards import (
        fast_lane_allowed,
        should_drop_message,
        standard_lane_allowed,
    )

    if should_drop_message(lane="route"):
        from app.ops.ledger.writer import record_dropped

        record_dropped(item, reason="emergency_halt_route")
        return None

    from app.ops.runtime.pipeline_gate import require_processing_or_skip

    if not require_processing_or_skip(component="priority_router"):
        from app.ops.ledger.writer import record_dropped

        record_dropped(item, reason="pipeline_gate_blocked")
        return None

    if get_lane_queues() is None:
        init_lane_queues()
        sync_legacy_worker_queues()

    runtime_dir = _runtime_dir(item)
    item = {**item, "ingested_at_unix": item.get("ingested_at_unix") or time.time()}

    gate = evaluate_editorial_gate(item)
    if not gate.allowed:
        from app.ops.ledger.writer import record_dropped

        log_editorial_drop(item, gate)
        persist_gate_rejection(runtime_dir, item, gate)
        record_dropped(item, reason=f"gatekeeper:{gate.reason}")
        return None
    item = apply_gate_boost(item, gate)

    suppressed, sim = should_suppress(item, runtime_dir=runtime_dir)
    if suppressed:
        from app.ops.ledger.writer import record_dropped

        logger.info("[ROUTE] SUPPRESS msg_id=%s similarity=%.2f", _item_id(item), sim)
        record_dropped(item, reason=f"suppress:{sim:.2f}")
        return None

    rank = score_item(item, runtime_dir=runtime_dir)
    chans = [str(item.get("source") or item.get("channel_name") or "")]
    escore = score_story(text=str(item.get("text") or ""), sources=chans, runtime_dir=runtime_dir)
    item = {
        **item,
        "editorial_rank": rank.to_dict(),
        "editorial_final_score": rank.final_score,
        "urgency_score": escore.urgency_score,
        "breaking_flag": escore.is_breaking,
    }

    decision = classify_lane(item, rank=rank, escore=escore)
    if breaking_override_mode() and decision.lane != Lane.FAST:
        decision = RoutingDecision(Lane.FAST, "breaking_override_promote", escore.urgency_score, True, rank.final_score)

    if decision.lane == Lane.FAST and not fast_lane_allowed():
        decision = RoutingDecision(
            Lane.STANDARD if standard_lane_allowed() else Lane.SLOW,
            "fast_lane_disabled",
            decision.urgency,
            decision.breaking,
            decision.final_score,
        )
    elif decision.lane in {Lane.STANDARD, Lane.SLOW} and not standard_lane_allowed():
        if fast_lane_allowed() and decision.breaking:
            decision = RoutingDecision(Lane.FAST, "fast_lane_only_promote", decision.urgency, True, decision.final_score)
        else:
            from app.ops.ledger.writer import record_dropped

            logger.info("[ROUTE] skip msg_id=%s reason=fast_lane_only", _item_id(item))
            record_dropped(item, reason="fast_lane_only")
            return None

    result = _enqueue_with_escalation(item, decision)
    if result is not None and not result.dropped:
        from app.ops.ledger.writer import record_routed

        record_routed(item, lane=result.lane.value, reason=result.reason)
    elif result is not None and result.dropped:
        from app.ops.ledger.writer import record_dropped

        record_dropped(item, reason=result.reason)
    return result


def schedule_route_message(item: dict[str, Any]) -> None:
    """Schedule routing on running event loop (collector-safe)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.call_soon(route_message_event, item)
