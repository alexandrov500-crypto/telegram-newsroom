from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass(frozen=True)
class AlertVerdict:
    surface: bool
    root_cause: str
    confidence: float
    probable_sources: tuple[str, ...]
    grouped_key: str
    reason: str


@dataclass
class AlertNoiseReducer:
    """Deduplicate, group, and rank alerts for operator focus."""

    repository: Week1Repository
    dedupe_sec: int = 900
    actionable_only: bool = True
    _recent_keys: dict[str, float] = field(default_factory=dict)
    _symptom_counts: dict[str, int] = field(default_factory=dict)

    def evaluate(
        self,
        *,
        title: str,
        severity: str,
        symptoms: list[str] | None = None,
        subsystem: str | None = None,
    ) -> AlertVerdict:
        symptoms = symptoms or []
        group_material = f"{subsystem or 'general'}:{':'.join(sorted(symptoms[:3]))}"
        grouped_key = hashlib.sha256(group_material.encode()).hexdigest()[:12]
        alert_key = hashlib.sha256(f"{severity}:{title}".encode()).hexdigest()[:16]

        now = time.monotonic()
        self._symptom_counts[grouped_key] = self._symptom_counts.get(grouped_key, 0) + 1
        repeat = self._symptom_counts[grouped_key]

        last = self._recent_keys.get(alert_key)
        deduped = last is not None and (now - last) < self.dedupe_sec

        root_cause = self._infer_root_cause(symptoms, subsystem)
        sources = self._rank_sources(symptoms, subsystem)
        confidence = 0.85 if root_cause != "unknown" else 0.55
        if repeat > 3:
            confidence = min(0.95, confidence + 0.05)

        surface = True
        reason = "actionable"
        if deduped:
            surface = False
            reason = "dedupe_window"
        elif repeat > 5 and severity not in ("critical", "CRITICAL"):
            surface = False
            reason = "repeated_symptom_suppressed"
        elif self.actionable_only and severity in ("info", "INFO") and repeat > 1:
            surface = False
            reason = "non_actionable_info"

        if surface:
            self._recent_keys[alert_key] = now

        self.repository.log_alert(
            alert_key=alert_key,
            severity=severity,
            root_cause=root_cause,
            confidence=confidence,
            suppressed=not surface,
            detail={
                "title": title[:200],
                "grouped_key": grouped_key,
                "probable_sources": list(sources),
                "reason": reason,
            },
        )
        return AlertVerdict(
            surface=surface,
            root_cause=root_cause,
            confidence=confidence,
            probable_sources=sources,
            grouped_key=grouped_key,
            reason=reason,
        )

    def noise_index(self) -> float:
        rows = self.repository.recent_alerts(limit=100)
        if not rows:
            return 0.0
        suppressed = sum(1 for r in rows if r.get("suppressed"))
        return suppressed / len(rows)

    def alert_quality_html(self) -> str:
        rows = self.repository.recent_alerts(limit=20)
        surfaced = [r for r in rows if not r.get("suppressed")]
        lines = [
            "<b>Alert quality</b>",
            f"Noise index: {self.noise_index():.0%} suppressed (recent)",
            f"Surfaced: {len(surfaced)} / {len(rows)}",
        ]
        for r in surfaced[:5]:
            lines.append(
                f"• {r.get('root_cause')} ({r.get('confidence', 0):.0%}) — {r.get('alert_key', '')[:8]}",
            )
        return "\n".join(lines)

    def noise_index_html(self) -> str:
        ni = self.noise_index()
        level = "low" if ni < 0.4 else "medium" if ni < 0.7 else "high"
        return f"<b>Noise index</b> {ni:.0%} ({level} suppression)"

    @staticmethod
    def _infer_root_cause(symptoms: list[str], subsystem: str | None) -> str:
        s = " ".join(symptoms).lower()
        if "floodwait" in s or "telegram" in s:
            return "telegram_pressure"
        if "openai" in s or "latency" in s:
            return "cognition_degradation"
        if "queue" in s or "backlog" in s:
            return "ingest_pressure"
        if "worker" in s or "crash" in s:
            return "worker_instability"
        if subsystem:
            return subsystem
        return "unknown"

    @staticmethod
    def _rank_sources(symptoms: list[str], subsystem: str | None) -> tuple[str, ...]:
        ranked: list[str] = []
        if subsystem:
            ranked.append(subsystem)
        for sym in symptoms[:3]:
            if sym not in ranked:
                ranked.append(sym)
        return tuple(ranked[:4])
