"""In-process breaking news fast lane (priority over normal batch ticks)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ops.pipeline.observability import emit_ops_event
from ops.pipeline.paths import pipeline_state_path

logger = logging.getLogger(__name__)

_queue: asyncio.PriorityQueue[tuple[float, int, dict[str, Any]]] | None = None
_seq = 0
_preempt_normal = False


@dataclass
class BreakingItem:
    article_id: str
    text: str
    sources: list[str]
    breaking_score: float
    priority_level: int = 9
    lane: str = "breaking"
    enqueued_at_unix: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "text": self.text[:500],
            "sources": self.sources,
            "breaking_score": self.breaking_score,
            "priority_level": self.priority_level,
            "lane": self.lane,
            "is_breaking": True,
            "enqueued_at_unix": self.enqueued_at_unix,
        }


def _get_queue() -> asyncio.PriorityQueue:
    global _queue
    if _queue is None:
        _queue = asyncio.PriorityQueue()
    return _queue


def enqueue_breaking(item: BreakingItem, *, runtime_dir: str | None = None) -> None:
    global _seq, _preempt_normal
    _seq += 1
    priority = -float(item.priority_level)
    _get_queue().put_nowait((priority, _seq, item.to_dict()))
    _preempt_normal = True
    emit_ops_event(
        "breaking_detected",
        runtime_dir=runtime_dir,
        news_id=item.article_id,
        state="breaking",
        decision_reason=f"score={item.breaking_score}",
        breaking_score=item.breaking_score,
    )
    path = pipeline_state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "breaking_enqueued", **item.to_dict()}, ensure_ascii=False) + "\n")
    logger.info("breaking lane enqueued article_id=%s score=%.2f", item.article_id, item.breaking_score)


def should_preempt_normal() -> bool:
    return _preempt_normal and not _get_queue().empty()


def queue_depth() -> int:
    return _get_queue().qsize()


async def drain_breaking_lane(
    handler: Any,
    *,
    max_items: int = 5,
    runtime_dir: str | None = None,
) -> int:
    """Process up to max_items with async handler(item_dict) -> None."""
    processed = 0
    q = _get_queue()
    while processed < max_items and not q.empty():
        _prio, _seq, payload = await q.get()
        try:
            await handler(payload)
            emit_ops_event(
                "breaking_processed",
                runtime_dir=runtime_dir,
                news_id=str(payload.get("article_id") or ""),
                state="breaking",
            )
        except Exception as exc:
            logger.warning("breaking lane handler failed: %s", exc)
        finally:
            q.task_done()
        processed += 1
    global _preempt_normal
    if q.empty():
        _preempt_normal = False
    return processed


def reset_breaking_lane_for_tests() -> None:
    global _queue, _seq, _preempt_normal
    _queue = None
    _seq = 0
    _preempt_normal = False
