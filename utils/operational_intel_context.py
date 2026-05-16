"""Shared read-only signal collection for operational intelligence tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from utils.operational_trends import TrendSample, load_history_dir, sample_from_runtime_signals
from utils.recovery_intelligence import build_recovery_assessment
from utils.scheduler_diagnostics import scheduler_diagnostics_snapshot


def collect_current_sample(
    *,
    output_dir: Path | None = None,
    settings: Any | None = None,
) -> TrendSample:
    od = output_dir or Path(os.environ.get("OUTPUT_DIR", "runtime_ops_output"))
    if settings is None:
        from app.config import load_settings

        settings = load_settings()
    from utils.runtime_drift_monitor import collect_runtime_signals

    sig = collect_runtime_signals(settings, output_dir=od)
    sched = scheduler_diagnostics_snapshot()
    return sample_from_runtime_signals(sig, scheduler_snap=sched)


def build_intel_context(
    *,
    output_dir: Path | None = None,
    history_dir: Path | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    od = output_dir or Path(os.environ.get("OUTPUT_DIR", "runtime_ops_output"))
    hist = history_dir or Path(os.environ.get("OPS_HISTORY_DIR", "var/ops_history"))
    current = collect_current_sample(output_dir=od, settings=settings)
    history = load_history_dir(hist)
    samples = history + [current] if not history or history[-1].captured_at != current.captured_at else history
    from utils.operational_trends import analyze_trends

    trends = analyze_trends(samples)
    recovery = build_recovery_assessment(od)
    return {
        "current": current,
        "samples": samples,
        "trends": trends,
        "recovery": recovery,
    }
