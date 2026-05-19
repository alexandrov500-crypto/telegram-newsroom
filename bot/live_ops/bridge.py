from __future__ import annotations

import logging
from typing import Any

from bot.live_ops.contracts import LiveEventType
from bot.live_ops.coordinator import LiveOpsCoordinator

logger = logging.getLogger(__name__)


async def emit_story_ingested(
    live_ops: LiveOpsCoordinator,
    *,
    story_id: int,
    source: str,
    correlation_id: str | None = None,
) -> None:
    await live_ops.event_bus.emit(
        LiveEventType.STORY_INGESTED,
        {"story_id": story_id, "source": source},
        node_id=live_ops.settings.node_id,
        correlation_id=correlation_id,
    )
    try:
        from bot.observability.metrics import record_story_lifecycle

        record_story_lifecycle("ingested")
    except Exception:
        pass


async def emit_publish_delivered(
    live_ops: LiveOpsCoordinator,
    *,
    pending_news_id: int,
    channel_id: int,
    message_id: int,
    correlation_id: str | None = None,
) -> None:
    with live_ops.telemetry.time_publish(channel_id=channel_id):
        await live_ops.event_bus.emit(
            LiveEventType.PUBLISH_DELIVERED,
            {
                "pending_news_id": pending_news_id,
                "channel_id": channel_id,
                "message_id": message_id,
            },
            node_id=live_ops.settings.node_id,
            correlation_id=correlation_id,
        )
    try:
        from bot.observability.metrics import record_story_lifecycle

        record_story_lifecycle("published")
    except Exception:
        pass


async def emit_rollout_changed(
    live_ops: LiveOpsCoordinator,
    *,
    stage: str,
    previous_stage: str,
) -> None:
    live_ops.telemetry.record_rollout_transition(previous_stage, stage)
    await live_ops.event_bus.emit(
        LiveEventType.ROLLOUT_CHANGED,
        {"stage": stage, "previous_stage": previous_stage},
        node_id=live_ops.settings.node_id,
    )


def wire_production_safety_hooks(
    live_ops: LiveOpsCoordinator,
    production_safety: Any,
) -> None:
    """Mirror rollout stage changes to the live event bus (non-breaking hook)."""

    rollout = getattr(production_safety, "rollout", None)
    if rollout is None:
        return

    original_set = rollout.set_stage

    def set_stage(stage: Any, *, reason: str = "operator") -> Any:
        prev = rollout.current_stage()
        result = original_set(stage, reason=reason)
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                emit_rollout_changed(
                    live_ops,
                    stage=result.value if hasattr(result, "value") else str(result),
                    previous_stage=prev.value if hasattr(prev, "value") else str(prev),
                ),
            )
        except Exception:
            logger.exception("event=live_ops_rollout_emit_failed")
        return result

    rollout.set_stage = set_stage  # type: ignore[method-assign]

    original_rollback = rollout.rollback_to_shadow

    def rollback_to_shadow(*, reason: str) -> Any:
        prev = rollout.current_stage()
        result = original_rollback(reason=reason)
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                emit_rollout_changed(
                    live_ops,
                    stage=result.value if hasattr(result, "value") else str(result),
                    previous_stage=prev.value if hasattr(prev, "value") else str(prev),
                ),
            )
        except Exception:
            logger.exception("event=live_ops_rollout_emit_failed")
        return result

    rollout.rollback_to_shadow = rollback_to_shadow  # type: ignore[method-assign]
