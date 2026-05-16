from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeAnomaly:
    severity: str  # info | warning | critical
    code: str
    message: str


def detect_runtime_anomalies(snapshot: dict[str, Any]) -> list[RuntimeAnomaly]:
    """
    Heuristic checks on a ``get_runtime_snapshot``-shaped dict (no I/O).
    """
    out: list[RuntimeAnomaly] = []
    metrics = snapshot.get("metrics") or {}
    counters = metrics.get("counters") if isinstance(metrics, dict) else None
    if not isinstance(counters, dict):
        counters = {}

    retries = int(counters.get("openai_retries", 0))
    if retries >= 40:
        out.append(
            RuntimeAnomaly(
                severity="warning",
                code="openai.excessive_retries",
                message=f"OpenAI retry counter is high ({retries}).",
            )
        )

    failures = int(counters.get("openai_failures", 0))
    if failures >= 8:
        out.append(
            RuntimeAnomaly(
                severity="critical",
                code="openai.repeated_failures",
                message=f"OpenAI failure counter elevated ({failures}).",
            )
        )

    sched = snapshot.get("scheduler") or {}
    if isinstance(sched, dict) and sched.get("tick_in_progress") is True:
        wall = float(sched.get("last_scheduler_wall_sec") or 0.0)
        if wall > 900:
            out.append(
                RuntimeAnomaly(
                    severity="critical",
                    code="scheduler.tick_stalled",
                    message=f"Tick still marked in progress with large last wall time ({wall:.1f}s).",
                )
            )
        else:
            out.append(
                RuntimeAnomaly(
                    severity="warning",
                    code="scheduler.tick_in_progress_flag",
                    message="Pipeline tick_in_progress flag is true (may indicate concurrent tick or stuck state).",
                )
            )

    tick = snapshot.get("tick_timings_last") or {}
    if isinstance(tick, dict):
        total = float(tick.get("collect_sec", 0) or 0) + float(tick.get("openai_sec", 0) or 0)
        if total > 600:
            out.append(
                RuntimeAnomaly(
                    severity="warning",
                    code="pipeline.abnormal_phase_duration",
                    message=f"Last tick phase timings sum to {total:.1f}s (collect+openai).",
                )
            )

    posts = int(snapshot.get("posts_collected_total", 0) or 0)
    drafts = int(snapshot.get("drafts_generated_total", 0) or 0)
    if posts > 5000 and drafts < 2:
        out.append(
            RuntimeAnomaly(
                severity="info",
                code="queue.ingestion_vs_drafts_skew",
                message=f"High posts_collected_total ({posts}) vs few drafts ({drafts}) — backlog or summarization bottleneck signal.",
            )
        )

    return out
