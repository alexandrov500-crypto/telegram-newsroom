"""Semantic breaking event collapse — prevent same-event spam."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ENTITY = re.compile(
    r"\b(Fed|ECB|BTC|ETH|Bitcoin|Putin|Trump|OPEC|sanctions|war|rate cut|rate hike|"
    r"ЦБ|ФРС|нефть|Путин|санкци|войн)\b",
    re.I,
)


@dataclass(frozen=True)
class BreakingCollapseVerdict:
    collapse: bool
    reason: str
    event_id: str
    is_update: bool


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "breaking_collapse_state.json"


def _window_sec() -> int:
    try:
        return max(600, int(os.getenv("BREAKING_COLLAPSE_WINDOW_SEC", "7200")))
    except ValueError:
        return 7200


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def event_fingerprint(text: str) -> str:
    entities = sorted({m.lower() for m in _ENTITY.findall(text or "")})
    tokens = re.findall(r"[a-zа-яё0-9]{5,}", (text or "").lower())[:20]
    blob = "|".join(entities + tokens[:12])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def evaluate_breaking_collapse(
    *,
    runtime_dir: str,
    text: str,
    source_handle: str = "",
) -> BreakingCollapseVerdict:
    now = time.time()
    fp = event_fingerprint(text)
    event_id = f"brk_evt:{fp}"

    try:
        state = json.loads(_state_path(runtime_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {"events": []}

    events: list[dict[str, Any]] = list(state.get("events") or [])
    recent = [e for e in events if now - float(e.get("ts") or 0) <= _window_sec()]

    ent_new = {m.lower() for m in _ENTITY.findall(text or "")}
    for e in recent:
        if str(e.get("event_id") or "") == event_id:
            return BreakingCollapseVerdict(True, "duplicate_fingerprint", event_id, True)
        prev_ents = set(e.get("entities") or [])
        if _similarity(ent_new, prev_ents) >= 0.65:
            return BreakingCollapseVerdict(True, "semantic_overlap", event_id, True)

    return BreakingCollapseVerdict(False, "new_event", event_id, False)


def record_breaking_event(
    *,
    runtime_dir: str,
    text: str,
    event_id: str,
    source_handle: str = "",
    message_id: int = 0,
) -> None:
    now = time.time()
    p = _state_path(runtime_dir)
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {"events": []}
    events = list(state.get("events") or [])
    events.insert(
        0,
        {
            "ts": now,
            "event_id": event_id,
            "entities": sorted({m.lower() for m in _ENTITY.findall(text or "")}),
            "source": (source_handle or "").lstrip("@").lower(),
            "message_id": int(message_id),
        },
    )
    state["events"] = events[:80]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")
