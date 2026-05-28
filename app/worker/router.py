"""Legacy router shim — delegates to app.ops.priority_router."""

from __future__ import annotations

from typing import Any

from app.ai.routing.priority import NewsPriority
from app.ops.queues import Lane
from app.ops.priority_router import route_message_event, schedule_route_message

schedule_route_item = schedule_route_message


def route_item(item: dict[str, Any]) -> NewsPriority | None:
    decision = route_message_event(item)
    if decision is None or decision.dropped:
        return None
    mapping = {
        Lane.FAST: NewsPriority.BREAKING,
        Lane.STANDARD: NewsPriority.HIGH,
        Lane.SLOW: NewsPriority.LOW,
    }
    return mapping.get(decision.lane, NewsPriority.NORMAL)


def _refresh_depths() -> None:
    from app.ops.queues import get_lane_queues
    from app.observability import ops_metrics as om

    reg = get_lane_queues()
    if reg is None:
        return
    d = reg.depths()
    om.record_queue_depths(fast=d["fast"], standard=d["standard"], slow=d["slow"])
