from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from bot.operator_console.formatting import clamp_lines, escape, format_header, now_utc_short
from bot.operator_console.severity import AlertLevel

DEFAULT_WINDOW_SEC = 120.0
MAX_SUMMARY_LINES = 10


@dataclass
class AggregateBuffer:
    kind: str
    window_sec: float
    severity: AlertLevel
    items: list[dict[str, Any]] = field(default_factory=list)
    window_start: float = field(default_factory=time.monotonic)
    cooldown_until: float = 0.0

    def add(self, payload: dict[str, Any]) -> None:
        self.items.append(payload)

    def expired(self) -> bool:
        return (time.monotonic() - self.window_start) >= self.window_sec

    def on_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def count(self) -> int:
        return len(self.items)

    @property
    def aggregation_id(self) -> str:
        """Deterministic ID from kind + window start + count (stable for replay)."""
        raw = f"{self.kind}|{int(self.window_start * 1000)}|{self.count()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


class NotificationAggregator:
    """Collapse noisy operator events into compact, replay-linked summaries."""

    _SEVERITY_BY_KIND: dict[str, AlertLevel] = {
        "ingest": AlertLevel.INFO,
        "contradiction": AlertLevel.WARNING,
        "replay_spike": AlertLevel.WARNING,
        "misinfo_cluster": AlertLevel.WARNING,
        "federation": AlertLevel.WARNING,
        "topology": AlertLevel.WARNING,
        "cognitive": AlertLevel.INFO,
    }

    def __init__(
        self,
        *,
        default_window_sec: float = DEFAULT_WINDOW_SEC,
        cooldown_sec: float = 30.0,
    ) -> None:
        self._default_window = default_window_sec
        self._cooldown_sec = cooldown_sec
        self._buffers: dict[str, AggregateBuffer] = {}

    def record(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        window_sec: float | None = None,
        severity: AlertLevel | None = None,
    ) -> AggregateBuffer:
        buf = self._buffers.get(kind)
        win = window_sec if window_sec is not None else self._default_window
        sev = severity or self._SEVERITY_BY_KIND.get(kind, AlertLevel.INFO)
        if buf is None or buf.expired():
            buf = AggregateBuffer(kind=kind, window_sec=win, severity=sev)
            self._buffers[kind] = buf
        buf.add(payload)
        return buf

    def ready_to_flush(self, kind: str, *, min_count: int = 3) -> bool:
        buf = self._buffers.get(kind)
        if buf is None or buf.on_cooldown():
            return False
        return buf.expired() or buf.count() >= min_count

    def flush(self, kind: str) -> tuple[str, str, int, AlertLevel] | None:
        buf = self._buffers.pop(kind, None)
        if buf is None or not buf.items:
            return None
        agg_id = buf.aggregation_id
        text = self._format_summary(kind, buf)
        buf.cooldown_until = time.monotonic() + self._cooldown_sec
        return text, agg_id, buf.count(), buf.severity

    def flush_all_ready(self) -> list[tuple[str, str, str, int, AlertLevel]]:
        out: list[tuple[str, str, str, int, AlertLevel]] = []
        for kind in list(self._buffers.keys()):
            if self.ready_to_flush(kind):
                flushed = self.flush(kind)
                if flushed:
                    md, agg_id, n, sev = flushed
                    out.append((kind, md, agg_id, n, sev))
        return out

    @staticmethod
    def _format_summary(kind: str, buf: AggregateBuffer) -> str:
        n = buf.count()
        agg = buf.aggregation_id
        sev_label = buf.severity.value

        if kind == "ingest":
            sources: dict[str, int] = defaultdict(int)
            for it in buf.items:
                sources[str(it.get("source", "?"))] += 1
            lines = [
                format_header("INGEST SUMMARY", sev_label),
                f"<b>{n}</b> items · replay <code>agg_{agg}</code>",
            ]
            for src, c in sorted(sources.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"{c}× {escape(src)}")
            lines.append(now_utc_short())
            return clamp_lines("\n".join(lines), max_lines=MAX_SUMMARY_LINES)

        if kind == "contradiction":
            buckets: dict[str, int] = defaultdict(int)
            for it in buf.items:
                subj = str(it.get("subject_type", "general"))
                expl = str(it.get("explanation", "")).lower()
                if "geo" in subj.lower() or "politic" in expl:
                    buckets["geopolitical"] += 1
                elif "source" in subj.lower():
                    buckets["source divergence"] += 1
                elif it.get("language_mismatch"):
                    buckets["multilingual"] += 1
                else:
                    buckets["other"] += 1
            lines = [
                format_header("CONTRADICTION SUMMARY", sev_label),
                f"<b>{n}</b> new contradictions",
                f"replay <code>agg_{agg}</code>",
            ]
            for label, c in sorted(buckets.items(), key=lambda x: -x[1]):
                if c:
                    lines.append(f"{c} {label}")
            lines.append("/contradictions_queue")
            return clamp_lines("\n".join(lines), max_lines=MAX_SUMMARY_LINES)

        if kind == "replay_spike":
            return clamp_lines(
                "\n".join(
                    [
                        format_header("REPLAY SPIKE", sev_label),
                        f"<b>{n}</b> pressure events",
                        f"replay <code>agg_{agg}</code>",
                        "/inspect_replay · /incident_timeline",
                    ]
                ),
                max_lines=MAX_SUMMARY_LINES,
            )

        if kind == "misinfo_cluster":
            return clamp_lines(
                "\n".join(
                    [
                        format_header("MISINFO CLUSTER", sev_label),
                        f"<b>{n}</b> related alerts",
                        f"replay <code>agg_{agg}</code>",
                        "→ epistemic review queue",
                    ]
                ),
                max_lines=MAX_SUMMARY_LINES,
            )

        if kind in ("federation", "topology"):
            tag = "FEDERATION INSTABILITY" if kind == "federation" else "TOPOLOGY INSTABILITY"
            regions: dict[str, int] = defaultdict(int)
            for it in buf.items:
                regions[str(it.get("region", it.get("node", "?")))] += 1
            lines = [
                format_header(tag, sev_label),
                f"<b>{n}</b> signals · <code>agg_{agg}</code>",
            ]
            for r, c in sorted(regions.items(), key=lambda x: -x[1])[:4]:
                lines.append(f"{c}× {escape(r)}")
            return clamp_lines("\n".join(lines), max_lines=MAX_SUMMARY_LINES)

        return clamp_lines(
            f"{format_header(kind.upper(), sev_label)}\n"
            f"<b>{n}</b> grouped · <code>agg_{agg}</code>",
            max_lines=MAX_SUMMARY_LINES,
        )


# Back-compat alias used by hub/tests
EventAggregator = NotificationAggregator
