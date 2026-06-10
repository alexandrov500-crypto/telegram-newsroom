"""Mode oscillation controller — prevent digest/breaking/synthesis lock-in."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.osgcp.arbitration_engine import FormatMode
from app.editorial.osgcp.config import mode_max_daily_pct


@dataclass(frozen=True)
class ModeOscillationResult:
    allowed: bool
    suggested_format: FormatMode
    dominant_mode: str
    dominant_pct: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "suggested_format": self.suggested_format.value,
            "dominant_mode": self.dominant_mode,
            "dominant_pct": round(self.dominant_pct, 3),
            "reason": self.reason,
        }


def evaluate_mode_oscillation(
    runtime_dir: str | None,
    *,
    proposed_format: FormatMode,
) -> ModeOscillationResult:
    from app.editorial.osgcp.state import load_state

    import time

    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    counts = dict(day.get("format_mode_counts") or {})
    total = sum(int(v) for v in counts.values())

    if total < 3:
        return ModeOscillationResult(True, proposed_format, "", 0.0, "insufficient_samples")

    max_pct = mode_max_daily_pct()
    dominant_mode = max(counts, key=lambda k: int(counts[k]))
    dominant_pct = int(counts.get(dominant_mode) or 0) / total

    proposed_key = proposed_format.value
    proposed_pct = int(counts.get(proposed_key) or 0) / total if total else 0.0

    if dominant_pct > max_pct and proposed_key == dominant_mode:
        cycle = ["signal", "context", "digest", "explainer"]
        try:
            idx = cycle.index(dominant_mode)
            next_fmt = FormatMode(cycle[(idx + 1) % len(cycle)])
        except (ValueError, KeyError):
            next_fmt = FormatMode.CONTEXT
        return ModeOscillationResult(
            False,
            next_fmt,
            dominant_mode,
            dominant_pct,
            "mode_lock_in_prevented",
        )

    if proposed_pct > max_pct:
        return ModeOscillationResult(
            False,
            FormatMode.CONTEXT,
            proposed_key,
            proposed_pct,
            "proposed_mode_over_cap",
        )

    return ModeOscillationResult(True, proposed_format, dominant_mode, dominant_pct, "oscillation_ok")
