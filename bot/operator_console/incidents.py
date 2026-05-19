from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from bot.operator_console.formatting import clamp_lines, escape, format_header, now_utc_short
from bot.operator_console.severity import AlertLevel, incident_dedupe_key


@dataclass
class IncidentThread:
    thread_id: str
    correlation_key: str
    severity: AlertLevel
    title: str
    events: list[dict[str, Any]] = field(default_factory=list)
    replay_refs: set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.monotonic)

    def append(self, *, detail: str, replay_ref: str | None = None, kind: str = "signal") -> None:
        self.events.append(
            {"at": now_utc_short(), "kind": kind, "detail": detail[:300]},
        )
        if replay_ref:
            self.replay_refs.add(replay_ref)

    def rca_snippet(self) -> str:
        chain = " → ".join(str(e.get("kind", "?")) for e in self.events[-4:])
        return chain or f"{len(self.events)} correlated signals"

    def suggested_action(self) -> str:
        kinds = {str(e.get("kind", "")) for e in self.events}
        if "replay" in kinds:
            return "inspect replay lane /incident_timeline " + self.thread_id
        if "contradiction" in kinds:
            return "review /contradictions_queue"
        if "federation" in kinds or "topology" in kinds:
            return "check /topology_live and mesh health"
        return "review incident thread and replay refs"

    def timeline_text(self, limit: int = 8) -> str:
        lines = [
            format_header("INCIDENT THREAD", self.severity.value),
            f"<code>{escape(self.thread_id)}</code>",
            f"<b>{escape(self.title)}</b>",
            escape(self.rca_snippet()),
            "",
        ]
        for ev in self.events[-limit:]:
            lines.append(f"• {ev['at']} {escape(ev['kind'])} — {escape(ev['detail'][:90])}")
        if self.replay_refs:
            refs = ", ".join(list(self.replay_refs)[:3])
            lines.append(f"Replay: <code>{escape(refs)}</code>")
        lines.append(f"Archaeology: <code>incident_{self.thread_id}</code>")
        lines.append(f"→ {escape(self.suggested_action())}")
        return clamp_lines("\n".join(lines), max_lines=12)


class IncidentCorrelator:
    """Thread related operational alerts under one incident ID."""

    _KEY_MAP = {
        "replay": "replay_pressure",
        "contradiction": "epistemic_contradiction",
        "confidence": "confidence_drift",
        "federation": "federation_mesh",
        "topology": "topology_churn",
        "storage": "storage_growth",
        "misinfo": "misinformation",
    }

    def __init__(self) -> None:
        self._threads: dict[str, IncidentThread] = {}

    def correlate(
        self,
        kind: str,
        *,
        title: str,
        detail: str,
        severity: AlertLevel,
        replay_ref: str | None = None,
    ) -> IncidentThread:
        key = self._correlation_key(kind, detail)
        existing = self._threads.get(key)
        if existing and (time.monotonic() - existing.created_at) < 3600:
            existing.append(detail=detail, replay_ref=replay_ref, kind=kind)
            if severity.rank > existing.severity.rank:
                existing.severity = severity
            return existing
        thread_id = f"inc_{hashlib.sha256(key.encode()).hexdigest()[:10]}"
        thread = IncidentThread(
            thread_id=thread_id,
            correlation_key=key,
            severity=severity,
            title=title,
        )
        thread.append(detail=detail, replay_ref=replay_ref, kind=kind)
        self._threads[key] = thread
        if len(self._threads) > 50:
            oldest = min(self._threads.values(), key=lambda t: t.created_at)
            self._threads.pop(oldest.correlation_key, None)
        return thread

    def get(self, thread_id: str) -> IncidentThread | None:
        for t in self._threads.values():
            if t.thread_id == thread_id:
                return t
        return None

    def _correlation_key(self, kind: str, detail: str) -> str:
        base = incident_dedupe_key(kind, detail)
        for token, mapped in self._KEY_MAP.items():
            if token in kind.lower() or token in detail.lower():
                return mapped
        return base

    def to_persist_dict(self, thread: IncidentThread) -> dict:
        return {
            "thread_id": thread.thread_id,
            "correlation_key": thread.correlation_key,
            "severity": thread.severity.value,
            "title": thread.title,
            "timeline_json": json.dumps(thread.events),
            "replay_refs_json": json.dumps(list(thread.replay_refs)),
        }
