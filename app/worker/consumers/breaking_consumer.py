"""Breaking fast lane: no clustering, minimal latency publish."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.observability.metrics import record_breaking_latency
from app.worker import queues
from app.worker.fast_publish import publish_breaking_item, quick_sanitize, schedule_post_publish_write
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_breaking_consumer(ctx: Any, *, stop_event: asyncio.Event) -> None:
    """Drain breaking queue; target end-to-end latency under ~3s."""
    from app.worker.queues import breaking_queue

    if breaking_queue is None:
        return

    bot = ctx.bot
    settings = ctx.settings

    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(breaking_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise

        t0 = time.perf_counter()
        try:
            from app.ops.control_plane.guards import publish_allowed_now, should_drop_message
            from app.ops.runtime.pipeline_gate import require_processing_or_skip

            if not require_processing_or_skip(component="breaking_consumer"):
                continue
            if should_drop_message(lane="fast"):
                continue
            ok_pub, pub_reason = publish_allowed_now()
            if not ok_pub:
                log_event(logger, "breaking.skip", reason=pub_reason, id=item.get("news_id"))
                continue

            text = quick_sanitize(str(item.get("text") or ""))
            source = str(item.get("source") or item.get("channel_name") or "?")
            article_id = str(item.get("news_id") or item.get("ingest_key") or "brk")
            sources = [
                {
                    "channel": source,
                    "message_id": item.get("message_id"),
                }
            ]
            if not text:
                log_event(logger, "breaking.skip", reason="empty_text", id=article_id)
                continue

            from app.editorial.gatekeeper import (
                evaluate_editorial_gate,
                log_editorial_drop,
                persist_gate_rejection,
            )

            gate = evaluate_editorial_gate(item)
            if not gate.allowed:
                log_editorial_drop(item, gate)
                persist_gate_rejection(settings.runtime_state_dir, item, gate)
                continue

            from app.editorial.desk_filter import evaluate_desk_filter
            from app.editorial.scoring_engine import score_story
            from app.publisher.draft_builder import build_draft_body

            ctx.is_breaking_stream = True
            escore = score_story(
                text=text,
                sources=[source],
                runtime_dir=settings.runtime_state_dir,
                editorial_override_breaking=True,
            )
            desk = evaluate_desk_filter(text, escore, sources=[source], runtime_dir=settings.runtime_state_dir)
            if not desk.publish and not desk.breaking_override:
                log_event(
                    logger,
                    "breaking.suppressed",
                    id=article_id,
                    reason=desk.reason,
                    quality=desk.quality_score,
                )
                continue

            body = build_draft_body(text, breaking=True, sources=sources, max_chars=1200)
            message_id = await publish_breaking_item(
                bot,
                settings,
                content=body,
                sources=sources,
                article_id=article_id,
            )
            from app.ops.control_plane.state import get_ops_store

            get_ops_store().record_publish_attempt(unix=time.time())
            latency = time.perf_counter() - t0
            record_breaking_latency(latency)
            from app.observability import editorial_metrics as em

            em.record_breaking_published_latency_ms(latency * 1000.0)
            schedule_post_publish_write(
                settings=settings,
                item=item,
                message_id=message_id,
                latency_sec=latency,
            )
            logger.info(
                "breaking lane published: id=%s latency=%.2fs message_id=%s",
                article_id,
                latency,
                message_id,
            )
        except Exception as exc:
            log_event(logger, "breaking.consumer_error", error=repr(exc)[:300])
            logger.warning("breaking consumer item failed: %s", exc)
        finally:
            breaking_queue.task_done()
            from app.worker.router import _refresh_depths

            _refresh_depths()
