from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bot.operator_ux.severity import AttentionSeverity


@dataclass
class AttentionItem:
    severity: AttentionSeverity
    category: str
    title: str
    detail: str = ""
    fingerprint: str = ""
    count: int = 1

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = fingerprint(self.category, self.title)


def fingerprint(category: str, title: str) -> str:
    raw = f"{category}:{re.sub(r'\s+', ' ', title.lower())[:120]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class BundleResult:
    delivered: list[AttentionItem] = field(default_factory=list)
    bundled: list[str] = field(default_factory=list)
    suppressed_count: int = 0


class AlertBundler:
    """In-memory window bundler; persists counts via repository when provided."""

    def __init__(self, *, window_minutes: int = 20) -> None:
        self._window_sec = window_minutes * 60
        self._seen: dict[str, tuple[float, AttentionItem]] = {}
        self.suppressed_total = 0
        self.bundled_total = 0

    def _prune(self) -> None:
        now = datetime.now(timezone.utc).timestamp()
        stale = [k for k, (ts, _) in self._seen.items() if now - ts > self._window_sec]
        for k in stale:
            del self._seen[k]

    def add(self, item: AttentionItem) -> AttentionItem | None:
        """Return item to deliver now, or None if suppressed into bundle."""
        self._prune()
        now = datetime.now(timezone.utc).timestamp()
        fp = item.fingerprint
        if fp in self._seen:
            ts, existing = self._seen[fp]
            existing.count += 1
            item.count = existing.count
            self._seen[fp] = (ts, existing)
            self.suppressed_total += 1
            self.bundled_total += 1
            return None
        self._seen[fp] = (now, item)
        return item

    def bundle_summary_lines(self) -> list[str]:
        """Summarize recurring issues in the window."""
        self._prune()
        by_cat: dict[str, list[AttentionItem]] = defaultdict(list)
        for _, item in self._seen.values():
            if item.count > 1:
                by_cat[item.category].append(item)
        lines: list[str] = []
        for cat, items in sorted(by_cat.items()):
            parts = [f"{it.title} ×{it.count}" for it in items[:4]]
            if parts:
                lines.append(f"{cat}: " + " · ".join(parts))
        return lines


def bundle_runtime_signals(pulse: dict[str, Any]) -> list[str]:
    """One-line bundled runtime instability summary."""
    parts: list[str] = []
    lag = float(pulse.get("event_loop_lag_max") or 0)
    if lag >= 0.15:
        parts.append(f"lag spikes (max {lag:.2f}s)")
    stalled = pulse.get("stalled_loops") or []
    if stalled:
        parts.append(f"{len(stalled)} stalled loops")
    recovery = int(pulse.get("recovery_attempt_count") or 0)
    if recovery:
        parts.append(f"{recovery} recovery")
    anomalies = pulse.get("anomalies") or []
    crit = sum(1 for a in anomalies if str(a.get("level", "")).lower() == "critical")
    if crit:
        parts.append(f"{crit} critical anomalies")
    if not parts:
        return []
    return [f"Runtime instability recurring: " + " · ".join(parts[:5])]
