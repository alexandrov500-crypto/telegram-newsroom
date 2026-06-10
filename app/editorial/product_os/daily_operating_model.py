"""Daily Product Operating Model — slot targets without volume inflation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.product_os.content_format import ContentFormat


class DailySlot(str, Enum):
    SIGNAL = "signal"
    CONTEXT = "context"
    MODEL = "model"
    DIGEST = "digest"
    SYNTHESIS = "synthesis"


_SLOT_TARGETS: dict[ContentFormat, tuple[int, int]] = {
    ContentFormat.SIGNAL: (1, 2),
    ContentFormat.CONTEXT: (2, 3),
    ContentFormat.MODEL: (1, 2),
    ContentFormat.DIGEST: (1, 1),
    ContentFormat.INSIGHT: (0, 2),
}


@dataclass(frozen=True)
class DailySlotDecision:
    slot: DailySlot
    within_daily_budget: bool
    recommend_digest: bool
    recommend_synthesis: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot.value,
            "within_daily_budget": self.within_daily_budget,
            "recommend_digest": self.recommend_digest,
            "recommend_synthesis": self.recommend_synthesis,
            "reason": self.reason,
        }


def _load_day_counts(runtime_dir: str | None) -> dict[str, int]:
    if not runtime_dir:
        return {}
    try:
        from app.editorial.product_os.state import load_state

        day_key = time.strftime("%Y-%m-%d", time.gmtime())
        day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
        return dict(day.get("format_counts") or {})
    except Exception:
        return {}


def evaluate_daily_slot(
    content_format: ContentFormat,
    *,
    runtime_dir: str | None = None,
    pg_total: float = 0.0,
    low_signal_day: bool = False,
) -> DailySlotDecision:
    counts = _load_day_counts(runtime_dir)
    fmt_key = content_format.value
    used = int(counts.get(fmt_key) or 0)
    lo, hi = _SLOT_TARGETS.get(content_format, (0, 3))
    within = used < hi

    slot_map = {
        ContentFormat.SIGNAL: DailySlot.SIGNAL,
        ContentFormat.CONTEXT: DailySlot.CONTEXT,
        ContentFormat.MODEL: DailySlot.MODEL,
        ContentFormat.DIGEST: DailySlot.DIGEST,
        ContentFormat.INSIGHT: DailySlot.CONTEXT,
    }
    slot = slot_map.get(content_format, DailySlot.CONTEXT)

    recommend_digest = low_signal_day and int(counts.get("digest") or 0) < 1
    recommend_synthesis = low_signal_day and pg_total < 55

    if not within and pg_total < 75:
        reason = "daily_slot_saturated_downgrade"
    elif recommend_synthesis:
        reason = "low_signal_synthesis"
    else:
        reason = "slot_available"

    return DailySlotDecision(
        slot=slot,
        within_daily_budget=within or pg_total >= 82,
        recommend_digest=recommend_digest,
        recommend_synthesis=recommend_synthesis,
        reason=reason,
    )
