from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bot.operator_console.fatigue import FatigueSnapshot


@dataclass
class UsabilityEvent:
    event_type: str
    severity: str
    signal_kind: str
    aggregated: bool = False
    suppressed: bool = False
    operator_action: str | None = None
    latency_ms: int | None = None
    at: float = field(default_factory=time.monotonic)


class UsabilityTelemetry:
    """Measure operator signal quality and fatigue trends."""

    def __init__(self) -> None:
        self._events: list[UsabilityEvent] = []
        self._actions: list[tuple[str, float]] = []

    def record_signal(
        self,
        *,
        signal_kind: str,
        severity: str,
        aggregated: bool = False,
        suppressed: bool = False,
    ) -> None:
        self._events.append(
            UsabilityEvent(
                event_type="signal",
                severity=severity,
                signal_kind=signal_kind,
                aggregated=aggregated,
                suppressed=suppressed,
            )
        )
        self._trim()

    def record_operator_action(self, action: str, *, latency_ms: int | None = None) -> None:
        self._actions.append((action, time.monotonic()))
        self._events.append(
            UsabilityEvent(
                event_type="operator_action",
                severity="info",
                signal_kind=action,
                operator_action=action,
                latency_ms=latency_ms,
            )
        )
        self._trim()

    def _trim(self, max_events: int = 2000) -> None:
        if len(self._events) > max_events:
            self._events = self._events[-max_events:]

    def report(self, fatigue: FatigueSnapshot) -> str:
        sent = [e for e in self._events if e.event_type == "signal" and not e.suppressed]
        suppressed = [e for e in self._events if e.suppressed]
        aggregated = [e for e in self._events if e.aggregated]
        by_kind: dict[str, int] = defaultdict(int)
        for e in sent:
            by_kind[e.signal_kind] += 1
        actions = len(self._actions)
        noise_ratio = len(suppressed) / max(len(sent) + len(suppressed), 1)
        lines = [
            "<b>Operator usability report</b>",
            f"Signals delivered: {len(sent)}",
            f"Suppressed (fatigue/agg): {len(suppressed)}",
            f"Aggregated summaries: {len(aggregated)}",
            f"Signal/noise ratio: {1 - noise_ratio:.2f}",
            f"Operator actions: {actions}",
            f"Fatigue score: {fatigue.score:.2f} ({fatigue.load_label})",
            "",
            "Top signal kinds:",
        ]
        for k, c in sorted(by_kind.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  • {k}: {c}")
        lines.append("\nRecommendations:")
        if noise_ratio > 0.4:
            lines.append("  • Raise TELEGRAM_LIVE_INGEST_MIN_PRIORITY or widen agg window")
        if fatigue.digest_mode:
            lines.append("  • Digest mode active — review CRITICAL thread only")
        if actions < 3 and len(sent) > 30:
            lines.append("  • High signal volume, low operator engagement — tune thresholds")
        return "\n".join(lines)

    def persist(self, repo: Any, fatigue: FatigueSnapshot) -> None:
        if repo is None:
            return
        try:
            repo.save_console_usability_snapshot(
                delivered=sum(1 for e in self._events if not e.suppressed),
                suppressed=sum(1 for e in self._events if e.suppressed),
                aggregated=sum(1 for e in self._events if e.aggregated),
                fatigue_score=fatigue.score,
                detail={"events": len(self._events)},
            )
        except Exception:
            pass

    def write_markdown(self, path: Path, fatigue: FatigueSnapshot) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.report(fatigue), encoding="utf-8")
        return path
