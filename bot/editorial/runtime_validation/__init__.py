from __future__ import annotations

from typing import Any

from bot.editorial.runtime_validation.baseline import (
    append_baseline_record,
    capture_operational_baseline,
    load_baseline_history,
)
from bot.editorial.runtime_validation.preservation import (
    build_monthly_stability_review,
    identify_dead_complexity_signals,
)
from bot.editorial.runtime_validation.report import build_runtime_validation_report


def runtime_validation_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    loop_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Long-horizon infrastructure verification — not a governance layer."""
    return build_runtime_validation_report(
        ctx=ctx,
        metrics=metrics,
        loop_snapshot=loop_snapshot,
    )


__all__ = [
    "runtime_validation_snapshot",
    "build_runtime_validation_report",
    "capture_operational_baseline",
    "append_baseline_record",
    "load_baseline_history",
    "build_monthly_stability_review",
    "identify_dead_complexity_signals",
]
